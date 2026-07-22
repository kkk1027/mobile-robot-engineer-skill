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
CLAIMS = {"complete", "partial", "planned"}


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


def validate(data: dict[str, Any], require_ran: bool, require_complete: bool) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile must be a JSON object")
    profile_name = str(profile.get("name", "")).strip()
    execution = str(profile.get("execution", "")).strip()
    kind = str(profile.get("kind", "")).strip()
    claim = str(profile.get("claim", "")).strip()
    if not profile_name:
        errors.append(issue("runtime.profile_name", "profile.name", "profile needs a name"))
    if execution not in EXECUTIONS:
        errors.append(issue("runtime.execution", "profile.execution", "execution must be ran or not_run"))
    if not kind:
        errors.append(issue("runtime.profile_kind", "profile.kind", "profile needs a kind"))
    if claim and claim not in CLAIMS:
        errors.append(issue("runtime.profile_claim", "profile.claim", "claim must be complete, partial, or planned"))
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
    observed_topics: dict[str, dict[str, Any]] = {}
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
        observed_topics[name] = topic
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

    coverage_gaps: list[dict[str, str]] = []
    required_topics = data.get("required_topics", [])
    if not isinstance(required_topics, list):
        raise ValueError("required_topics must be a list")
    if (require_complete or claim == "complete") and not required_topics:
        errors.append(issue("runtime.required_topics_empty", "required_topics", "complete acceptance needs at least one declared required topic"))
    required_names: set[str] = set()
    for index, requirement in enumerate(required_topics):
        path = f"required_topics[{index}]"
        if not isinstance(requirement, dict):
            errors.append(issue("runtime.required_topic", path, "required topic must be an object"))
            continue
        name = str(requirement.get("name", "")).strip()
        min_hz = requirement.get("min_hz")
        if not name:
            errors.append(issue("runtime.required_topic_name", f"{path}.name", "required topic needs a name"))
            continue
        if name in required_names:
            errors.append(issue("runtime.duplicate_required_topic", f"{path}.name", "required topic name must be unique"))
            continue
        required_names.add(name)
        if min_hz is not None and not positive_number(min_hz):
            errors.append(issue("runtime.required_topic_rate", f"{path}.min_hz", "required topic minimum frequency must be positive"))
            continue
        observed = observed_topics.get(name)
        gap: dict[str, str] | None = None
        if observed is None:
            gap = issue("runtime.required_topic_missing", f"{path}.name", f"required topic {name} is not observed in this profile")
        elif ran:
            observed_hz = observed.get("observed_hz")
            if not nonnegative_number(observed_hz):
                gap = issue("runtime.required_topic_unmeasured", f"topics.{name}.observed_hz", f"required topic {name} needs a measured frequency")
            elif positive_number(min_hz) and observed_hz < min_hz:
                gap = issue("runtime.required_topic_below_minimum", f"topics.{name}.observed_hz", f"required topic {name} is below its declared minimum")
            elif not str(observed.get("measurement_source", "")).strip():
                gap = issue("runtime.required_topic_evidence", f"topics.{name}.measurement_source", f"required topic {name} needs measurement evidence")
        if gap is not None:
            coverage_gaps.append(gap)

    for gap in coverage_gaps:
        if require_complete:
            errors.append(gap)
        else:
            warnings.append(gap)
    if claim == "complete" and coverage_gaps:
        errors.append(issue("runtime.claim_overstated", "profile.claim", "complete claim has unmet required topic coverage"))

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

    actions = data.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("actions must be a list")
    action_results: list[dict[str, Any]] = []
    seen_actions: set[str] = set()
    for index, action in enumerate(actions):
        path = f"actions[{index}]"
        if not isinstance(action, dict):
            errors.append(issue("runtime.action", path, "action relation must be an object"))
            continue
        name = str(action.get("name", "")).strip()
        clients = string_list(action.get("clients"))
        servers = string_list(action.get("servers"))
        if not name:
            errors.append(issue("runtime.action_name", f"{path}.name", "action relation needs a name"))
            continue
        if name in seen_actions:
            errors.append(issue("runtime.duplicate_action", f"{path}.name", "action relation name must be unique"))
        seen_actions.add(name)
        if clients is None or not clients:
            errors.append(issue("runtime.action_clients", f"{path}.clients", "action relation needs observed clients"))
            clients = []
        if servers is None or not servers:
            errors.append(issue("runtime.action_servers", f"{path}.servers", "action relation needs observed servers"))
            servers = []
        unknown = sorted(set(clients + servers) - set(component_state))
        if unknown:
            errors.append(issue("runtime.action_component", path, f"action relation references unknown components: {', '.join(unknown)}"))
        if ran and not str(action.get("measurement_source", "")).strip():
            errors.append(issue("runtime.action_measurement_source", f"{path}.measurement_source", "ran action relation needs measurement evidence"))
        action_results.append({"name": name, "clients": clients, "servers": servers})

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
        "profile": {"name": profile_name, "kind": kind, "execution": execution, "claim": claim or None},
        "topics": topic_results,
        "required_topic_coverage_complete": not coverage_gaps,
        "required_topic_coverage_gaps": coverage_gaps,
        "critical_flows": flow_results,
        "actions": action_results,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--require-ran", action="store_true", help="fail unless profile execution is ran")
    parser.add_argument("--require-complete", action="store_true", help="fail if a required topic is missing, unmeasured, or below its minimum")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.observation.resolve()), args.require_ran, args.require_complete)
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
