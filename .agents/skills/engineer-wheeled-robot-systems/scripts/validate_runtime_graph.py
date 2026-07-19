#!/usr/bin/env python3
"""Validate that a declared robot runtime graph closes required command/feedback flows."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


L2_ROLES = {
    "robot_spawn", "motion_source", "command_supervisor", "actuator",
    "feedback", "state_estimation", "health_gate", "motion_authorizer",
}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime graph must be a JSON object")
    return value


def topic(value: str) -> str:
    return "topic:" + value.strip()


def component(value: str) -> str:
    return "component:" + value.strip()


def reachable(graph: dict[str, set[str]], start: str, goal: str) -> bool:
    queue = deque([start])
    seen = {start}
    while queue:
        current = queue.popleft()
        if current == goal:
            return True
        for child in graph.get(current, set()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return False


def validate_profile(name: str, profile: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    components = profile.get("components")
    if not isinstance(components, list):
        raise ValueError(f"profiles.{name}.components must be a list")
    graph: dict[str, set[str]] = defaultdict(set)
    roles: dict[str, list[str]] = defaultdict(list)
    component_inputs: dict[str, list[str]] = {}
    producers: dict[str, list[str]] = defaultdict(list)
    consumers: dict[str, list[str]] = defaultdict(list)
    names: set[str] = set()
    for item in components:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            issues.append({"code": "graph.component", "path": name, "message": "component needs a name"})
            continue
        node = str(item["name"]).strip()
        if node in names:
            issues.append({"code": "graph.duplicate_component", "path": f"{name}.{node}", "message": "duplicate component"})
        names.add(node)
        component_inputs[node] = [str(value) for value in item.get("consumes", [])]
        for role in item.get("roles", []):
            roles[str(role)].append(node)
        for interface in item.get("produces", []):
            graph[component(node)].add(topic(str(interface)))
            producers[str(interface)].append(node)
        for interface in item.get("consumes", []):
            graph[topic(str(interface))].add(component(node))
            consumers[str(interface)].append(node)

    required_roles = set(profile.get("required_roles", []))
    if str(profile.get("target_level", "")).upper() == "L2":
        required_roles.update(L2_ROLES)
    for role in sorted(required_roles):
        if not roles.get(role):
            issues.append({"code": "graph.missing_role", "path": f"{name}.roles.{role}", "message": "required runtime role has no component"})
    default_unique_roles = ["command_supervisor"] if str(profile.get("target_level", "")).upper() == "L2" else []
    for role in profile.get("unique_roles", default_unique_roles):
        owners = roles.get(str(role), [])
        if len(owners) != 1:
            issues.append({"code": "graph.unique_role", "path": f"{name}.roles.{role}", "message": f"expected one owner, found {len(owners)}"})

    flows = profile.get("required_flows", [])
    if str(profile.get("target_level", "")).upper() == "L2" and not flows:
        issues.append({"code": "graph.required_flow", "path": name, "message": "L2 profile needs at least one declared closed-loop flow"})
    flow_results = []
    for flow in flows:
        start = str(flow.get("from", ""))
        goal = str(flow.get("to", ""))
        ok = bool(start and goal and reachable(graph, topic(start), topic(goal)))
        flow_results.append({"name": flow.get("name", "unnamed"), "from": start, "to": goal, "reachable": ok})
        if start and not producers.get(start):
            issues.append({"code": "graph.flow_source", "path": f"{name}.flows.{flow.get('name', 'unnamed')}", "message": "flow start interface has no producer"})
        if not ok:
            issues.append({"code": "graph.unreachable_flow", "path": f"{name}.flows.{flow.get('name', 'unnamed')}", "message": "required interface flow is not reachable"})

    for interface in profile.get("required_gate_topics", []):
        interface = str(interface)
        if not producers.get(interface):
            issues.append({"code": "graph.gate_producer", "path": f"{name}.{interface}", "message": "gate topic has no producer"})
        if not consumers.get(interface):
            issues.append({"code": "graph.gate_consumer", "path": f"{name}.{interface}", "message": "gate topic has no consumer"})
    if str(profile.get("target_level", "")).upper() == "L2":
        for owner in roles.get("health_gate", []):
            if not component_inputs.get(owner):
                issues.append({"code": "graph.health_inputs", "path": f"{name}.{owner}", "message": "L2 health gate must consume runtime evidence rather than publish a constant"})
    return {
        "ok": not issues,
        "component_count": len(names),
        "roles": dict(sorted(roles.items())),
        "flows": flow_results,
        "issues": issues,
    }


def validate(data: dict[str, Any]) -> dict[str, Any]:
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("profiles must be a non-empty JSON object")
    results = {name: validate_profile(name, value) for name, value in profiles.items() if isinstance(value, dict)}
    if len(results) != len(profiles):
        raise ValueError("every profile must be a JSON object")
    return {
        "schema_version": 1,
        "ok": all(result["ok"] for result in results.values()),
        "profiles": results,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.manifest.resolve()))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
