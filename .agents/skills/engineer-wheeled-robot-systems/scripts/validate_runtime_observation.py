#!/usr/bin/env python3
"""Validate observed runtime connectivity, timing, and TF ownership for a robot profile."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


DISPOSITIONS = {"in_critical_flow", "observability_only", "disabled"}
EXECUTIONS = {"ran", "not_run"}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime observation must be a JSON object")
    return value


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return [item.strip() for item in value]


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def validate(data: dict[str, Any], require_ran: bool) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile must be a JSON object")
    profile_name = str(profile.get("name", "")).strip()
    execution = str(profile.get("execution", "")).strip()
    kind = str(profile.get("kind", "")).strip()
    if not profile_name:
        errors.append(issue("runtime.profile_name", "profile.name", "profile needs a name"))
    if execution not in EXECUTIONS:
        errors.append(issue("runtime.execution", "profile.execution", "execution must be ran or not_run"))
    if not kind:
        errors.append(issue("runtime.profile_kind", "profile.kind", "profile needs a kind"))
    ran = execution == "ran"
    if ran:
        if not positive_number(profile.get("wall_clock_window_s")):
            errors.append(issue("runtime.window", "profile.wall_clock_window_s", "ran profile needs a positive wall-clock window"))
        if not str(profile.get("measurement_source", "")).strip():
            errors.append(issue("runtime.measurement_source", "profile.measurement_source", "ran profile needs measurement evidence"))
        if kind == "simulation":
            if not nonnegative_number(profile.get("real_time_factor")):
                errors.append(issue("runtime.rtf", "profile.real_time_factor", "ran simulation needs observed real_time_factor"))
            if not positive_number(profile.get("min_real_time_factor")):
                errors.append(issue("runtime.min_rtf", "profile.min_real_time_factor", "ran simulation needs a positive minimum RTF"))
            elif nonnegative_number(profile.get("real_time_factor")) and profile["real_time_factor"] < profile["min_real_time_factor"]:
                errors.append(issue("runtime.rtf_below_minimum", "profile.real_time_factor", "observed RTF is below this profile's declared minimum"))
    else:
        warnings.append(issue("runtime.not_run", "profile.execution", "schema is valid but no runtime claim may be made"))
        if require_ran:
            errors.append(issue("runtime.require_ran", "profile.execution", "this validation requires an observed run"))

    components = data.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("components must be a non-empty list")
    component_state: dict[str, tuple[str, str]] = {}
    for index, component in enumerate(components):
        path = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(issue("runtime.component", path, "component must be an object"))
            continue
        name = str(component.get("name", "")).strip()
        state = str(component.get("state", "")).strip()
        disposition = str(component.get("disposition", "")).strip()
        if not name:
            errors.append(issue("runtime.component_name", path, "component needs a name"))
            continue
        if name in component_state:
            errors.append(issue("runtime.duplicate_component", path, "component name must be unique"))
            continue
        if state not in {"active", "inactive", "unknown"}:
            errors.append(issue("runtime.component_state", f"{path}.state", "state must be active, inactive, or unknown"))
        if disposition not in DISPOSITIONS:
            errors.append(issue("runtime.component_disposition", f"{path}.disposition", "disposition must be in_critical_flow, observability_only, or disabled"))
        if state == "active" and disposition == "disabled":
            errors.append(issue("runtime.active_disabled", path, "active component cannot be declared disabled"))
        component_state[name] = (state, disposition)

    topics = data.get("topics")
    if not isinstance(topics, list):
        raise ValueError("topics must be a list")
    connections: dict[tuple[str, str], list[str]] = defaultdict(list)
    topic_results: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for index, topic in enumerate(topics):
        path = f"topics[{index}]"
        if not isinstance(topic, dict):
            errors.append(issue("runtime.topic", path, "topic must be an object"))
            continue
        name = str(topic.get("name", "")).strip()
        publishers = string_list(topic.get("publishers"))
        subscribers = string_list(topic.get("subscribers"))
        if not name:
            errors.append(issue("runtime.topic_name", path, "topic needs a name"))
            continue
        if name in seen_topics:
            errors.append(issue("runtime.duplicate_topic", path, "topic name must be unique"))
        seen_topics.add(name)
        if publishers is None or not publishers:
            errors.append(issue("runtime.publishers", f"{path}.publishers", "topic needs observed publishers"))
            publishers = []
        if subscribers is None:
            errors.append(issue("runtime.subscribers", f"{path}.subscribers", "topic subscribers must be a string list"))
            subscribers = []
        unknown = sorted(set(publishers + subscribers) - set(component_state))
        if unknown:
            errors.append(issue("runtime.topic_component", path, f"topic references unknown components: {', '.join(unknown)}"))
        for publisher in publishers:
            for subscriber in subscribers:
                connections[(publisher, subscriber)].append(name)
        required_min_hz = topic.get("required_min_hz")
        observed_hz = topic.get("observed_hz")
        if required_min_hz is not None:
            if not positive_number(required_min_hz):
                errors.append(issue("runtime.required_rate", f"{path}.required_min_hz", "required minimum frequency must be positive"))
            if ran and not nonnegative_number(observed_hz):
                errors.append(issue("runtime.observed_rate", f"{path}.observed_hz", "ran measured topic needs observed frequency"))
            if ran and not str(topic.get("measurement_source", "")).strip():
                errors.append(issue("runtime.topic_measurement_source", f"{path}.measurement_source", "measured topic needs evidence"))
            if positive_number(required_min_hz) and nonnegative_number(observed_hz) and observed_hz < required_min_hz:
                errors.append(issue("runtime.rate_below_minimum", f"{path}.observed_hz", "observed frequency is below declared minimum"))
        topic_results.append({"name": name, "publishers": publishers, "subscribers": subscribers})

    flows = data.get("critical_flows")
    if not isinstance(flows, list) or not flows:
        raise ValueError("critical_flows must be a non-empty list")
    critical_components: set[str] = set()
    flow_results: list[dict[str, Any]] = []
    for index, flow in enumerate(flows):
        path = f"critical_flows[{index}]"
        if not isinstance(flow, dict):
            errors.append(issue("runtime.flow", path, "critical flow must be an object"))
            continue
        name = str(flow.get("name", "")).strip() or f"flow_{index}"
        members = string_list(flow.get("components"))
        if members is None or len(members) < 2:
            errors.append(issue("runtime.flow_components", f"{path}.components", "critical flow needs at least two ordered components"))
            continue
        missing = sorted(set(members) - set(component_state))
        if missing:
            errors.append(issue("runtime.flow_component", path, f"flow references unknown components: {', '.join(missing)}"))
            continue
        critical_components.update(members)
        edges: list[dict[str, Any]] = []
        for source, destination in zip(members, members[1:]):
            matched_topics = sorted(connections.get((source, destination), []))
            edges.append({"from": source, "to": destination, "topics": matched_topics})
            if not matched_topics:
                errors.append(issue("runtime.flow_edge", path, f"no observed topic connects {source} to {destination}"))
        flow_results.append({"name": name, "components": members, "edges": edges})

    for name, (state, disposition) in sorted(component_state.items()):
        if state == "active" and disposition == "in_critical_flow" and name not in critical_components:
            errors.append(issue("runtime.dead_branch", f"components.{name}", "active critical component is not represented in any critical flow"))

    tf_edges = data.get("dynamic_tf", [])
    if not isinstance(tf_edges, list):
        raise ValueError("dynamic_tf must be a list")
    for index, edge in enumerate(tf_edges):
        path = f"dynamic_tf[{index}]"
        if not isinstance(edge, dict):
            errors.append(issue("runtime.tf", path, "dynamic TF edge must be an object"))
            continue
        parent = str(edge.get("parent", "")).strip()
        child = str(edge.get("child", "")).strip()
        broadcasters = string_list(edge.get("broadcasters"))
        if not parent or not child:
            errors.append(issue("runtime.tf_frame", path, "dynamic TF edge needs parent and child"))
        if broadcasters is None or len(broadcasters) != 1:
            errors.append(issue("runtime.tf_owner", f"{path}.broadcasters", "dynamic TF edge needs exactly one observed broadcaster"))
        elif broadcasters[0] not in component_state:
            errors.append(issue("runtime.tf_component", f"{path}.broadcasters", "TF broadcaster must be a declared component"))

    ready = ran and not errors
    return {
        "schema_version": 1,
        "ok": not errors,
        "observed_ready": ready,
        "profile": {"name": profile_name, "kind": kind, "execution": execution},
        "topics": topic_results,
        "critical_flows": flow_results,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--require-ran", action="store_true", help="fail unless profile execution is ran")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.observation.resolve()), args.require_ran)
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
