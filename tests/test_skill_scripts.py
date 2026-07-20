from __future__ import annotations

import json
import hashlib
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
INTEGRATION = REPO / "tests" / "fixtures" / "integration"
INTEGRATION_MANIFEST = INTEGRATION / "module_manifest.json"
INTEGRATION_CONTRACT = INTEGRATION / "integration_contract.json"
REQUIREMENTS_TRACE = INTEGRATION / "requirements_trace.json"


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
        self.assertEqual(data["base_type_scope"], "mentioned_or_supported_not_active_configuration")
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

    def test_incomplete_source_snapshot_is_inconclusive_and_active_base_is_unknown(self) -> None:
        solution = {"base_type": "differential", "features": ["emergency_stop"]}
        inventory = {
            "schema_version": 2,
            "base_types": ["omni"],
            "base_type_scope": "mentioned_or_supported_not_active_configuration",
            "ros": [], "languages": [], "frameworks": [], "packages": [],
            "package_roles": [], "interfaces": [], "features": [], "evidence": {},
        }
        availability = {"whitelisted_file_count": 20, "available_file_count": 7}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            solution_path = root / "solution.json"
            inventory_path = root / "inventory.json"
            availability_path = root / "availability.json"
            solution_path.write_text(json.dumps(solution), encoding="utf-8")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            availability_path.write_text(json.dumps(availability), encoding="utf-8")
            result = run_script(
                "compare_solution_to_inventory.py", str(solution_path), str(inventory_path),
                "--source-availability", str(availability_path),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["summary"]["static_ratio_status"], "inconclusive_incomplete_source_snapshot")
        self.assertFalse(data["summary"]["source_snapshot_coverage"]["complete_enough_for_static_ratio"])
        self.assertIsNone(data["base_type"]["matched"])
        self.assertEqual(data["base_type"]["status"], "tool_unknown_active_variant")
        self.assertEqual(data["summary"]["safety_missing_status"], "tool_unknown_due_to_incomplete_source_snapshot")

    def test_generation_trace_covers_every_fact_and_checks_evidence(self) -> None:
        intake = {
            "allowed_input": {
                "hardware_devices": {
                    "base_type": "differential",
                    "wheel_radius_m": {"value": 0.07, "provenance": "test_default_simulation_only"},
                },
                "project_direction": ["indoor navigation"],
            }
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            intake_path = root / "intake.json"
            evidence = root / "robot_contract.json"
            intake_path.write_text(json.dumps(intake), encoding="utf-8")
            evidence.write_text("{}", encoding="utf-8")
            trace = {
                "intake_sha256": hashlib.sha256(intake_path.read_bytes()).hexdigest(),
                "facts": {
                    "hardware_devices.base_type": {
                        "disposition": "used", "evidence": ["robot_contract.json"],
                    },
                    "hardware_devices.wheel_radius_m": {
                        "disposition": "used", "scope": "simulation_only",
                        "evidence": ["robot_contract.json"],
                    },
                    "project_direction[0]": {
                        "disposition": "used", "evidence": ["robot_contract.json"],
                    },
                },
            }
            trace_path = root / "trace.json"
            trace_path.write_text(json.dumps(trace), encoding="utf-8")
            result = run_script(
                "validate_generation_trace.py", str(intake_path), str(trace_path),
                "--project-root", str(root),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            trace["facts"].pop("hardware_devices.base_type")
            trace_path.write_text(json.dumps(trace), encoding="utf-8")
            failed = run_script("validate_generation_trace.py", str(intake_path), str(trace_path))
        self.assertEqual(failed.returncode, 1)
        self.assertIn("trace.missing_fact", {item["code"] for item in json.loads(failed.stdout)["issues"]})

    def test_runtime_graph_requires_reachable_l2_closed_loop(self) -> None:
        graph = {
            "profiles": {
                "simulation": {
                    "target_level": "L2",
                    "components": [
                        {"name": "spawn", "roles": ["robot_spawn"], "consumes": [], "produces": []},
                        {"name": "test_source", "roles": ["motion_source"], "consumes": [], "produces": ["/request"]},
                        {"name": "supervisor", "roles": ["command_supervisor"], "consumes": ["/request", "/health", "/authorized"], "produces": ["/safe"]},
                        {"name": "sim_base", "roles": ["actuator", "feedback"], "consumes": ["/safe"], "produces": ["/wheel_odom"]},
                        {"name": "estimator", "roles": ["state_estimation"], "consumes": ["/wheel_odom"], "produces": ["/local_state"]},
                        {"name": "health", "roles": ["health_gate"], "consumes": ["/local_state"], "produces": ["/health"]},
                        {"name": "authorizer", "roles": ["motion_authorizer"], "consumes": [], "produces": ["/authorized"]},
                    ],
                    "required_gate_topics": ["/health", "/authorized"],
                    "required_flows": [{"name": "motion_feedback", "from": "/request", "to": "/local_state"}],
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runtime_graph.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            result = run_script("validate_runtime_graph.py", str(path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            graph["profiles"]["simulation"]["components"] = [
                item for item in graph["profiles"]["simulation"]["components"]
                if item["name"] != "estimator"
            ]
            path.write_text(json.dumps(graph), encoding="utf-8")
            failed = run_script("validate_runtime_graph.py", str(path))
        self.assertEqual(failed.returncode, 1)
        issues = json.loads(failed.stdout)["profiles"]["simulation"]["issues"]
        codes = {item["code"] for item in issues}
        self.assertIn("graph.missing_role", codes)
        self.assertIn("graph.unreachable_flow", codes)

    def test_module_manifest_candidate_generation_and_driver_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_path = root / "inventory.json"
            scan = run_script(
                "inspect_ros_workspace.py", str(FIXTURE), "--output", str(inventory_path)
            )
            self.assertEqual(scan.returncode, 0, scan.stderr)
            generated = run_script("create_module_manifest.py", str(inventory_path))
        self.assertEqual(generated.returncode, 0, generated.stderr)
        candidate = json.loads(generated.stdout)
        self.assertEqual(candidate["modules"][0]["state"], "candidate")
        self.assertEqual(candidate["modules"][0]["classification"], "blocked")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidate_manifest.json"
            path.write_text(json.dumps(candidate), encoding="utf-8")
            candidate_check = run_script("validate_module_manifest.py", str(path))
        self.assertEqual(candidate_check.returncode, 0, candidate_check.stdout + candidate_check.stderr)
        self.assertIn("module.candidate", {item["code"] for item in json.loads(candidate_check.stdout)["warnings"]})
        valid = run_script("validate_module_manifest.py", str(INTEGRATION_MANIFEST))
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        manifest = json.loads(INTEGRATION_MANIFEST.read_text(encoding="utf-8"))
        manifest["modules"][0]["verification"] = [
            item for item in manifest["modules"][0]["verification"]
            if item["kind"] != "safety_default"
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "driver_without_safety.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            failed = run_script("validate_module_manifest.py", str(path))
        self.assertEqual(failed.returncode, 1)
        codes = {item["code"] for item in json.loads(failed.stdout)["errors"]}
        self.assertIn("driver.baseline", codes)

    def test_empty_module_manifest_is_inconclusive_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty_manifest.json"
            path.write_text(json.dumps({"schema_version": 1, "modules": []}), encoding="utf-8")
            result = run_script("validate_module_manifest.py", str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        codes = {item["code"] for item in json.loads(result.stdout)["warnings"]}
        self.assertIn("manifest.empty", codes)

    def test_integration_contract_checks_type_adapter_and_command_authority(self) -> None:
        valid = run_script(
            "validate_integration_contract.py", str(INTEGRATION_CONTRACT),
            "--module-manifest", str(INTEGRATION_MANIFEST),
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        manifest = json.loads(INTEGRATION_MANIFEST.read_text(encoding="utf-8"))
        for module in manifest["modules"]:
            if module["id"] == "navigation":
                module["interfaces"][0]["type"] = "std_msgs/msg/String"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mismatched_manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            failed = run_script(
                "validate_integration_contract.py", str(INTEGRATION_CONTRACT),
                "--module-manifest", str(path),
            )
        self.assertEqual(failed.returncode, 1)
        codes = {item["code"] for item in json.loads(failed.stdout)["errors"]}
        self.assertIn("connection.type_mismatch", codes)

    def test_requirements_trace_requires_integration_evidence_for_complete_p1(self) -> None:
        valid = run_script(
            "validate_requirements_trace.py", str(REQUIREMENTS_TRACE),
            "--module-manifest", str(INTEGRATION_MANIFEST),
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        trace = json.loads(REQUIREMENTS_TRACE.read_text(encoding="utf-8"))
        trace["requirements"][0]["verification"][0]["level"] = "unit"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unit_only_trace.json"
            path.write_text(json.dumps(trace), encoding="utf-8")
            failed = run_script(
                "validate_requirements_trace.py", str(path),
                "--module-manifest", str(INTEGRATION_MANIFEST),
            )
        self.assertEqual(failed.returncode, 1)
        codes = {item["code"] for item in json.loads(failed.stdout)["errors"]}
        self.assertIn("requirement.integration_evidence", codes)

    def test_reference_links_exist(self) -> None:
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        import re

        links = re.findall(r"\]\((references/[^)]+)\)", skill_text)
        self.assertGreaterEqual(len(links), 8)
        for link in links:
            self.assertTrue((SKILL / link).is_file(), link)
        self.assertTrue((SKILL / "references" / "secondary-development-and-integration.md").is_file())

    def test_openai_metadata_mentions_skill(self) -> None:
        metadata = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "轮式机器人工程师"', metadata)
        self.assertIn("$engineer-wheeled-robot-systems", metadata)
        self.assertIn("集成", metadata)

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
