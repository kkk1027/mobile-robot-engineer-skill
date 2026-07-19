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
        self.assertGreaterEqual(data["summary"]["static_match_ratio"], 0.9)
        self.assertEqual(data["summary"]["safety_missing_static_evidence"], [])

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
