#!/usr/bin/env python3
"""Validate a JSON robot-system contract without running ROS or hardware."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BASE_TYPES = {
    "differential", "skid_steer", "ackermann", "mecanum",
    "omni", "swerve", "articulated", "special_wheeled",
}
REQUIRED_SECTIONS = {"system", "frames", "interfaces", "timing", "safety"}
SAFETY_KEYS_REAL = {
    "emergency_stop",
    "hardware_watchdog",
    "command_timeout",
    "motion_requires_authorization",
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


def load_contract(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".json":
        raise ValueError("v0 validator accepts JSON only")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top-level contract must be an object")
    return value


def add(
    issues: list[Issue],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(Issue(severity, code, path, message))


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate_frames(frames: Any, issues: list[Issue]) -> None:
    if not isinstance(frames, dict):
        add(issues, "error", "frames.type", "frames", "frames must be an object")
        return
    edges = frames.get("edges")
    if not isinstance(edges, list) or not edges:
        add(issues, "error", "frames.edges.required", "frames.edges", "provide at least one TF edge")
        return
    parents: dict[str, str] = {}
    graph: dict[str, list[str]] = {}
    normalized: set[tuple[str, str]] = set()
    for index, edge in enumerate(edges):
        path = f"frames.edges[{index}]"
        if not isinstance(edge, list) or len(edge) != 2 or not all(isinstance(x, str) and x for x in edge):
            add(issues, "error", "frames.edge.shape", path, "edge must be [parent, child]")
            continue
        parent, child = edge
        if parent == child:
            add(issues, "error", "frames.self_loop", path, "parent and child must differ")
            continue
        if child in parents and parents[child] != parent:
            add(
                issues,
                "error",
                "frames.multiple_parents",
                path,
                f"{child} already has parent {parents[child]}",
            )
        parents[child] = parent
        graph.setdefault(parent, []).append(child)
        normalized.add((parent, child))

    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        status = state.get(node, 0)
        if status == 1:
            return True
        if status == 2:
            return False
        state[node] = 1
        for child in graph.get(node, []):
            if visit(child):
                return True
        state[node] = 2
        return False

    if any(visit(node) for node in list(graph)):
        add(issues, "error", "frames.cycle", "frames.edges", "TF graph contains a cycle")
    if ("odom", "base_link") not in normalized and ("odom", "base_footprint") not in normalized:
        add(
            issues,
            "error",
            "frames.local_chain",
            "frames.edges",
            "expected odom->base_link or odom->base_footprint",
        )
    all_frames = {frame for edge in normalized for frame in edge}
    if "map" in all_frames and ("map", "odom") not in normalized:
        add(issues, "warning", "frames.map_chain", "frames.edges", "map is present without map->odom")

    owners = frames.get("dynamic_owners", {})
    if not isinstance(owners, dict):
        add(issues, "error", "frames.owners.type", "frames.dynamic_owners", "must be an object")
    else:
        for parent, child in normalized:
            edge_name = f"{parent}->{child}"
            if parent in {"map", "odom"} and edge_name not in owners:
                add(
                    issues,
                    "warning",
                    "frames.owner.missing",
                    f"frames.dynamic_owners.{edge_name}",
                    "declare the dynamic TF owner",
                )


def validate_interfaces(interfaces: Any, issues: list[Issue]) -> list[dict[str, Any]]:
    if not isinstance(interfaces, list) or not interfaces:
        add(issues, "error", "interfaces.required", "interfaces", "provide interface contracts")
        return []
    valid: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, interface in enumerate(interfaces):
        path = f"interfaces[{index}]"
        if not isinstance(interface, dict):
            add(issues, "error", "interface.type", path, "interface must be an object")
            continue
        name = interface.get("name")
        kind = interface.get("kind")
        msg_type = interface.get("type")
        direction = interface.get("direction")
        if not isinstance(name, str) or not name.startswith("/"):
            add(issues, "error", "interface.name", f"{path}.name", "use an absolute interface name")
        if kind not in {"topic", "service", "action"}:
            add(issues, "error", "interface.kind", f"{path}.kind", "kind must be topic, service, or action")
        if not isinstance(msg_type, str) or "/" not in msg_type:
            add(issues, "error", "interface.message_type", f"{path}.type", "declare the ROS interface type")
        if direction not in {"command", "feedback", "sensor", "state", "diagnostic", "request"}:
            add(issues, "warning", "interface.direction", f"{path}.direction", "declare a recognized direction")
        key = (str(kind), str(name))
        if key in seen:
            add(issues, "error", "interface.duplicate", path, f"duplicate interface {key}")
        seen.add(key)
        if kind == "topic":
            if not positive_number(interface.get("rate_hz")):
                add(issues, "error", "interface.rate", f"{path}.rate_hz", "topic rate_hz must be positive")
            if direction in {"command", "sensor", "feedback", "state"} and not positive_number(interface.get("max_age_ms")):
                add(issues, "error", "interface.max_age", f"{path}.max_age_ms", "declare positive max_age_ms")
            qos = interface.get("qos")
            if not isinstance(qos, dict):
                add(issues, "warning", "interface.qos", f"{path}.qos", "declare QoS")
            else:
                if qos.get("reliability") not in {"reliable", "best_effort"}:
                    add(issues, "warning", "interface.qos.reliability", f"{path}.qos.reliability", "declare reliable or best_effort")
                if not positive_number(qos.get("depth")):
                    add(issues, "warning", "interface.qos.depth", f"{path}.qos.depth", "declare positive history depth")
        valid.append(interface)
    commands = [item for item in valid if item.get("direction") == "command"]
    feedback = [item for item in valid if item.get("direction") in {"feedback", "state"}]
    if not commands:
        add(issues, "error", "interfaces.command", "interfaces", "at least one motion command interface is required")
    if not feedback:
        add(issues, "error", "interfaces.feedback", "interfaces", "at least one feedback/state interface is required")
    return valid


def validate_timing(timing: Any, issues: list[Issue]) -> None:
    if not isinstance(timing, dict):
        add(issues, "error", "timing.type", "timing", "timing must be an object")
        return
    required = {"control_rate_hz", "command_timeout_ms", "stop_timeout_ms"}
    for key in required:
        if not positive_number(timing.get(key)):
            add(issues, "error", f"timing.{key}", f"timing.{key}", "must be positive")
    command_timeout = timing.get("command_timeout_ms")
    stop_timeout = timing.get("stop_timeout_ms")
    if positive_number(command_timeout) and positive_number(stop_timeout):
        if stop_timeout < command_timeout:
            add(
                issues,
                "warning",
                "timing.stop_before_stale",
                "timing.stop_timeout_ms",
                "stop timeout is shorter than command stale timeout; confirm semantics",
            )
        if stop_timeout > 2000:
            add(
                issues,
                "warning",
                "timing.stop_slow",
                "timing.stop_timeout_ms",
                "stopping later than 2 s requires explicit hazard justification",
            )


def validate_base_dofs(system: dict[str, Any], interfaces: list[dict[str, Any]], issues: list[Issue]) -> None:
    base_type = system.get("base_type")
    dofs = system.get("command_dofs")
    if not isinstance(dofs, list) or not all(isinstance(value, str) for value in dofs):
        add(issues, "warning", "system.command_dofs", "system.command_dofs", "declare commanded DOFs")
        return
    dof_set = set(dofs)
    if base_type in {"differential", "skid_steer", "ackermann"} and "vy" in dof_set:
        add(issues, "error", "system.infeasible_vy", "system.command_dofs", f"{base_type} cannot command lateral velocity directly")
    if base_type in {"mecanum", "omni", "swerve"} and not {"vx", "vy", "wz"}.issubset(dof_set):
        add(issues, "warning", "system.missing_holonomic_dofs", "system.command_dofs", f"{base_type} normally exposes vx, vy, wz")
    if base_type == "ackermann":
        names = {item.get("name") for item in interfaces}
        if not any("ackermann" in str(name).lower() or "drive" in str(name).lower() for name in names):
            add(issues, "warning", "system.ackermann_interface", "interfaces", "confirm an Ackermann speed/steering command interface")


def validate_contract(contract: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for section in sorted(REQUIRED_SECTIONS - contract.keys()):
        add(issues, "error", "section.missing", section, f"missing required section {section}")
    system = contract.get("system")
    if not isinstance(system, dict):
        add(issues, "error", "system.type", "system", "system must be an object")
        system = {}
    base_type = system.get("base_type")
    if base_type not in BASE_TYPES:
        add(issues, "error", "system.base_type", "system.base_type", f"choose one of {sorted(BASE_TYPES)}")
    if system.get("ros") not in {"ros2", "ros1", "hybrid"}:
        add(issues, "error", "system.ros", "system.ros", "ros must be ros2, ros1, or hybrid")
    deployment = system.get("deployment")
    if deployment not in {"simulation", "real", "both"}:
        add(issues, "error", "system.deployment", "system.deployment", "deployment must be simulation, real, or both")

    validate_frames(contract.get("frames"), issues)
    interfaces = validate_interfaces(contract.get("interfaces"), issues)
    validate_timing(contract.get("timing"), issues)
    validate_base_dofs(system, interfaces, issues)

    safety = contract.get("safety")
    if not isinstance(safety, dict):
        add(issues, "error", "safety.type", "safety", "safety must be an object")
    else:
        required = SAFETY_KEYS_REAL if deployment in {"real", "both"} else {"command_timeout"}
        for key in sorted(required):
            if safety.get(key) is not True:
                add(issues, "error", f"safety.{key}", f"safety.{key}", "must be true for this deployment")
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="robot contract JSON")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        contract = load_contract(args.contract.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    issues = validate_contract(contract)
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    result = {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "issues": [asdict(issue) for issue in issues],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
