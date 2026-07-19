from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / ".agents" / "skills" / "engineer-wheeled-robot-systems"
SCRIPTS = SKILL / "scripts"
FIXTURE = REPO / "tests" / "fixtures" / "mini_diff_ws"
CONTRACT = FIXTURE / "src" / "mini_diff_robot" / "config" / "robot_contract.json"
SOLUTION = REPO / "evals" / "scenarios" / "mini-diff-solution.json"
GENERATED_CONTRACT = (
    REPO / "evals" / "results" / "diff-jetson-stm32-gazebo-contract.json"
)


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )


class SkillScriptTests(unittest.TestCase):
    def test_inventory_detects_fixture(self) -> None:
        result = run_script("inspect_ros_workspace.py", str(FIXTURE))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("ros2", data["ros"])
        self.assertIn("differential", data["base_types"])
        self.assertIn("ros2_control", data["frameworks"])
        self.assertIn("gazebo", data["frameworks"])
        self.assertEqual({p["name"] for p in data["packages"]}, {"mini_diff_robot"})
        for interface in ("/cmd_vel", "/odom", "/diagnostics"):
            self.assertIn(interface, data["interfaces"])
        for feature in ("command_timeout", "emergency_stop", "watchdog", "simulation"):
            self.assertIn(feature, data["features"])
        for role in ("bringup", "control", "description", "monitoring", "simulation"):
            self.assertIn(role, data["package_roles"])
        self.assertNotIn("can", data["hardware"])
        self.assertEqual(data["security_findings"], [])

    def test_inventory_redacts_possible_secret(self) -> None:
        fake_value = "unit-fixture-value-1234"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config.py").write_text(
                f'api_token = "{fake_value}"  # micro_ros_agent\n',
                encoding="utf-8",
            )
            result = run_script("inspect_ros_workspace.py", str(root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(fake_value, result.stdout)
        findings = json.loads(result.stdout)["security_findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["excerpt"], "[REDACTED]")

    def test_intake_levels_and_test_default_gate(self) -> None:
        intake = {
            "allowed_input": {
                "hardware_devices": {
                    "base": {
                        "type": "two_wheel_differential",
                        "wheel_radius_m": {
                            "value": 0.05,
                            "provenance": "test_default_simulation_only",
                        },
                        "wheel_separation_m": {
                            "value": 0.30,
                            "provenance": "user_confirmed",
                        },
                    },
                    "current_upper_compute": "industrial PC",
                    "drive": {
                        "motor": "DC geared motor",
                        "driver": "dual H bridge",
                    },
                    "encoders": {"counts_per_wheel_revolution": 2048},
                    "sensors": {
                        "lidar": {
                            "model": "generic 2D lidar",
                            "xyz_m": [0.1, 0.0, 0.2],
                            "rpy_rad": [0.0, 0.0, 0.0],
                        }
                    },
                    "battery": {"rated_voltage_v": 24},
                    "physical_emergency_stop": {
                        "value": "unresolved",
                        "provenance": "unresolved_real",
                    },
                    "network": "Ethernet and UART",
                },
                "technical_stack": ["ROS 2", "C++", "Gazebo"],
                "project_direction": ["indoor autonomous navigation"],
                "execution_boundary": {"test_profile": "simulation acceptance"},
            }
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "intake.json"
            path.write_text(json.dumps(intake), encoding="utf-8")
            result = run_script(
                "validate_project_intake.py",
                str(path),
                "--target-level",
                "L3",
            )
        self.assertEqual(result.returncode, 1, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["level_eligibility"]["L1"]["input_ready"])
        self.assertTrue(data["level_eligibility"]["L2"]["input_ready"])
        self.assertFalse(data["level_eligibility"]["L3"]["input_ready"])
        self.assertIn("hardware_devices.base.wheel_radius_m", data["unsafe_provenance_paths"])
        self.assertNotIn("unit-fixture", result.stdout)

    def test_valid_contract_passes(self) -> None:
        result = run_script("validate_robot_contract.py", str(CONTRACT))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_generated_solution_contract_passes(self) -> None:
        result = run_script(
            "validate_robot_contract.py",
            str(GENERATED_CONTRACT),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_invalid_contract_fails(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["system"]["command_dofs"].append("vy")
        contract["safety"]["hardware_watchdog"] = False
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            result = run_script("validate_robot_contract.py", str(path))
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        codes = {issue["code"] for issue in data["issues"]}
        self.assertIn("system.infeasible_vy", codes)
        self.assertIn("safety.hardware_watchdog", codes)

    def test_solution_comparison_has_safety_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            inventory_path = Path(temp) / "inventory.json"
            scan = run_script(
                "inspect_ros_workspace.py",
                str(FIXTURE),
                "--output",
                str(inventory_path),
            )
            self.assertEqual(scan.returncode, 0, scan.stderr)
            result = run_script(
                "compare_solution_to_inventory.py",
                str(SOLUTION),
                str(inventory_path),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["base_type"]["matched"])
        self.assertGreaterEqual(data["summary"]["semantic_static_match_ratio"], 0.9)
        self.assertTrue(data["summary"]["package_name_overlap_is_informational"])
        self.assertEqual(data["summary"]["safety_missing_static_evidence"], [])

    def test_solution_comparison_normalizes_interface_slashes(self) -> None:
        solution = json.loads(SOLUTION.read_text(encoding="utf-8"))
        solution["interfaces"] = [name.lstrip("/") for name in solution["interfaces"]]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_path = root / "inventory.json"
            solution_path = root / "solution.json"
            solution_path.write_text(json.dumps(solution), encoding="utf-8")
            scan = run_script(
                "inspect_ros_workspace.py",
                str(FIXTURE),
                "--output",
                str(inventory_path),
            )
            self.assertEqual(scan.returncode, 0, scan.stderr)
            result = run_script(
                "compare_solution_to_inventory.py",
                str(solution_path),
                str(inventory_path),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        compared = json.loads(result.stdout)
        self.assertEqual(compared["comparisons"]["interfaces"]["missing_static_evidence"], [])

    def test_reference_links_exist(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        import re

        links = re.findall(r"\]\((references/[^)]+)\)", skill_text)
        self.assertGreaterEqual(len(links), 8)
        for link in links:
            self.assertTrue((SKILL / link).is_file(), link)

    def test_openai_metadata_mentions_skill(self) -> None:
        metadata = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "轮式机器人工程师"', metadata)
        self.assertIn("$engineer-wheeled-robot-systems", metadata)

    def test_scenarios_are_wheeled(self) -> None:
        scenario_dir = REPO / "evals" / "scenarios"
        scenarios = [
            path for path in scenario_dir.glob("*.json")
            if path.name != "mini-diff-solution.json"
        ]
        self.assertEqual(len(scenarios), 4)
        for path in scenarios:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(
                data["expected_routes"]["base_type"],
                {"differential", "mecanum", "ackermann", "swerve"},
            )


if __name__ == "__main__":
    unittest.main()
