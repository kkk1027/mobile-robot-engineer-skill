#!/usr/bin/env python3
"""Generate a best-effort, read-only inventory of a ROS repository or workspace."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "build",
    "install",
    "log",
    "node_modules",
    ".venv",
    "venv",
}
TEXT_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp",
    ".py", ".xml", ".launch", ".yaml", ".yml", ".json",
    ".urdf", ".xacro", ".sdf", ".world", ".rviz", ".toml",
    ".md", ".txt", ".cmake", ".sh", ".bash",
}
MAX_TEXT_BYTES = 2 * 1024 * 1024

ROS_SIGNALS = {
    "ros2": [
        r"\brclcpp\b", r"\brclpy\b", r"\bament_(?:cmake|python)\b",
        r"\bros2_control\b", r"\bcontroller_manager\b", r"\bros2\s+launch\b",
    ],
    "ros1": [
        r"\brospy\b", r"\broscpp\b", r"\bcatkin\b", r"\broslaunch\b",
        r"\bros::NodeHandle\b",
    ],
}
FRAMEWORK_SIGNALS = {
    "nav2": [r"\bnav2_", r"\bnav2\b"],
    "slam_toolbox": [r"\bslam_toolbox\b"],
    "cartographer": [r"\bcartographer\b"],
    "robot_localization": [r"\brobot_localization\b", r"\bekf_(?:localization_)?node\b"],
    "ros2_control": [r"\bros2_control\b", r"\bcontroller_manager\b", r"\bhardware_interface\b"],
    "micro_ros": [r"\bmicro[-_]?ros\b", r"\bmicro_ros_agent\b"],
    "gazebo": [r"\bgazebo\b", r"\bros_gz\b", r"\bgz_sim\b"],
    "isaac_sim": [r"\bisaac sim\b", r"\bomni\.isaac\b", r"\bisaac_ros\b"],
    "mujoco": [r"\bmujoco\b", r"\bMJCF\b"],
    "move_base": [r"\bmove_base\b"],
}
BASE_SIGNALS = {
    "differential": [r"\bdiff(?:erential)?[_ -]?drive\b", r"\bdiff_drive_controller\b", r"\b2wd\b", r"\b4wd\b"],
    "skid_steer": [r"\bskid[_ -]?steer\b", r"\bskid4wd\b"],
    "ackermann": [r"\backermann\b", r"\bbicycle model\b", r"\bsteering_angle\b"],
    "mecanum": [r"\bmecanum\b"],
    "omni": [r"\bomni[_ -]?wheel\b", r"\bomnidirectional\b"],
    "swerve": [r"\bswerve\b", r"\bsteering[_ -]?module\b"],
    "articulated": [r"\barticulated[_ -]?steer\b", r"\brocker[_ -]?bogie\b"],
}
HARDWARE_SIGNALS = {
    "jetson": [r"\bjetson\b", r"\btegra\b"],
    "industrial_pc": [r"\bindustrial pc\b", r"\bipc\b"],
    "stm32": [r"\bstm32\b"],
    "esp32": [r"\besp32\b"],
    "teensy": [r"\bteensy\b"],
    "can": [r"\bCAN(?:-FD)?\b", r"\bsocketcan\b", r"\bcan[0-9]\b"],
    "serial": [r"\bserial\b", r"\btty(?:USB|ACM)\b", r"\bUART\b"],
    "ethercat": [r"\bethercat\b"],
    "lidar": [r"\blidar\b", r"\blaser_scan\b", r"\bsensor_msgs/(?:msg/)?LaserScan\b"],
    "camera": [r"\bcamera\b", r"\bimage_transport\b"],
    "imu": [r"\bimu\b", r"\bsensor_msgs/(?:msg/)?Imu\b"],
    "gnss": [r"\bgnss\b", r"\bgps\b", r"\bNavSatFix\b"],
}
FEATURE_SIGNALS = {
    "command_timeout": [r"\bcmd_vel_timeout\b", r"\bcommand_timeout\b", r"\btimeout.*cmd"],
    "emergency_stop": [r"\be[_ -]?stop\b", r"\bemergency[_ -]?stop\b"],
    "watchdog": [r"\bwatchdog(?:\b|_)", r"\bheartbeat(?:\b|_)"],
    "simulation": [r"\buse_sim_time\b", r"\bsimulation\b", r"\bgazebo\b", r"\bros_gz\b"],
    "diagnostics": [r"\bdiagnostic_msgs\b", r"\bdiagnostic_updater\b"],
    "lifecycle": [r"\bLifecycleNode\b", r"\brclcpp_lifecycle\b", r"\blifecycle_manager\b"],
    "mapping": [r"\bslam\b", r"\bmapping\b"],
    "localization": [r"\bamcl\b", r"\blocalization\b", r"\bekf\b"],
    "navigation": [r"\bnav2\b", r"\bmove_base\b", r"\bplanner\b"],
}
INTERFACE_KEYWORDS = re.compile(
    r"(create_publisher|create_subscription|create_service|create_client|"
    r"create_server|create_wall_timer|advertise|subscribe|Service|Action|"
    r"ros2\s+(?:topic|service|action))",
    re.IGNORECASE,
)
QUOTED = re.compile(r"""["']([^"']+)["']""")
INTERFACE_VALUE = re.compile(r"^/?[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z0-9_]+)+$")
COMMON_INTERFACES = {
    "cmd_vel", "odom", "scan", "tf", "tf_static", "joint_states",
    "imu", "camera_info", "map", "diagnostics",
}


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path, warnings: list[str]) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            warnings.append(f"skipped oversized text candidate: {path.name}")
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        warnings.append(f"could not read {path}: {exc}")
        return None


def package_info(package_xml: Path, root: Path, warnings: list[str]) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": package_xml.parent.name,
        "path": relative_path(package_xml.parent, root),
        "version": None,
        "build_type": None,
        "dependencies": [],
    }
    try:
        tree = ET.parse(package_xml)
        node = tree.getroot()
        name = node.findtext("name")
        version = node.findtext("version")
        if name:
            info["name"] = name.strip()
        if version:
            info["version"] = version.strip()
        deps: set[str] = set()
        for tag in (
            "depend", "build_depend", "buildtool_depend", "exec_depend",
            "test_depend", "build_export_depend",
        ):
            for dep in node.findall(tag):
                if dep.text and dep.text.strip():
                    deps.add(dep.text.strip())
        info["dependencies"] = sorted(deps)
        export = node.find("export")
        if export is not None:
            build_type = export.findtext("build_type")
            if build_type:
                info["build_type"] = build_type.strip()
        if not info["build_type"]:
            if (package_xml.parent / "setup.py").exists():
                info["build_type"] = "ament_python_or_catkin_python"
            elif (package_xml.parent / "CMakeLists.txt").exists():
                info["build_type"] = "cmake_unknown"
    except (ET.ParseError, OSError) as exc:
        warnings.append(f"could not parse {relative_path(package_xml, root)}: {exc}")
    return info


def add_evidence(
    evidence: dict[str, dict[str, list[dict[str, Any]]]],
    category: str,
    value: str,
    file_name: str,
    line: int,
    excerpt: str,
) -> None:
    bucket = evidence[category][value]
    if len(bucket) >= 8:
        return
    bucket.append({"file": file_name, "line": line, "excerpt": excerpt[:240]})


def scan_signals(
    text: str,
    file_name: str,
    evidence: dict[str, dict[str, list[dict[str, Any]]]],
) -> set[str]:
    interfaces: set[str] = set()
    interface_window = 0
    compiled_groups = {
        "ros": {key: [re.compile(p, re.I) for p in pats] for key, pats in ROS_SIGNALS.items()},
        "frameworks": {key: [re.compile(p, re.I) for p in pats] for key, pats in FRAMEWORK_SIGNALS.items()},
        "base_types": {key: [re.compile(p, re.I) for p in pats] for key, pats in BASE_SIGNALS.items()},
        "hardware": {key: [re.compile(p, re.I) for p in pats] for key, pats in HARDWARE_SIGNALS.items()},
        "features": {key: [re.compile(p, re.I) for p in pats] for key, pats in FEATURE_SIGNALS.items()},
    }
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        for category, values in compiled_groups.items():
            for value, patterns in values.items():
                if any(pattern.search(line) for pattern in patterns):
                    add_evidence(evidence, category, value, file_name, line_no, stripped)
        if INTERFACE_KEYWORDS.search(line):
            interface_window = 4
        if interface_window > 0:
            for candidate in QUOTED.findall(line):
                normalized = candidate.strip()
                bare = normalized.lstrip("/")
                if INTERFACE_VALUE.match(normalized) or bare in COMMON_INTERFACES:
                    interface = normalized if normalized.startswith("/") else f"/{normalized}"
                    interfaces.add(interface)
                    add_evidence(evidence, "interfaces", interface, file_name, line_no, stripped)
            interface_window -= 1
    return interfaces


def inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    warnings: list[str] = []
    files = list(iter_files(root))
    packages = [
        package_info(path, root, warnings)
        for path in files
        if path.name == "package.xml"
    ]
    evidence: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    suffix_counts: Counter[str] = Counter()
    languages: set[str] = set()
    interfaces: set[str] = set()
    launch_files: list[str] = []
    config_files: list[str] = []
    description_files: list[str] = []
    interface_definition_files: list[str] = []

    for path in files:
        rel = relative_path(path, root)
        suffix = path.suffix.lower()
        suffix_counts[suffix or "<none>"] += 1
        if suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}:
            languages.add("cpp")
        elif suffix == ".py":
            languages.add("python")
        if "launch" in path.parts or ".launch." in path.name or suffix == ".launch":
            launch_files.append(rel)
        if suffix in {".yaml", ".yml", ".json", ".toml"}:
            config_files.append(rel)
        if suffix in {".urdf", ".xacro", ".sdf", ".world"}:
            description_files.append(rel)
        if suffix in {".msg", ".srv", ".action"}:
            interface_definition_files.append(rel)
        if suffix not in TEXT_SUFFIXES and path.name not in {"CMakeLists.txt", "package.xml"}:
            continue
        text = read_text(path, warnings)
        if text is None:
            continue
        interfaces.update(scan_signals(text, rel, evidence))

    def detected(category: str) -> list[str]:
        return sorted(value for value, hits in evidence.get(category, {}).items() if hits)

    return {
        "schema_version": 1,
        "root": str(root),
        "ros": detected("ros"),
        "languages": sorted(languages),
        "frameworks": detected("frameworks"),
        "base_types": detected("base_types"),
        "hardware": detected("hardware"),
        "features": detected("features"),
        "packages": sorted(packages, key=lambda item: item["name"]),
        "interfaces": sorted(interfaces),
        "files": {
            "total": len(files),
            "by_suffix": dict(sorted(suffix_counts.items())),
            "launch": sorted(launch_files),
            "config": sorted(config_files),
            "description": sorted(description_files),
            "interface_definitions": sorted(interface_definition_files),
        },
        "evidence": {
            category: dict(values)
            for category, values in evidence.items()
        },
        "warnings": sorted(set(warnings)),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="ROS repository or workspace root")
    parser.add_argument("--output", type=Path, help="write JSON to this file")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.path.resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    result = inventory(root)
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
