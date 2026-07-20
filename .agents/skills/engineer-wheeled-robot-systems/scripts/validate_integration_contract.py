"""Validate module wiring, TF ownership and command authority for ROS integration."""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get(field), list):
        raise ValueError(f"{path.name}.{field} must be a list")
    return value


def issue(items: list[dict[str, str]], code: str, path: str, message: str) -> None:
    items.append({"code": code, "path": path, "message": message})


def split_ref(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or value.count(".") != 1:
        return None
    module, interface = value.split(".", 1)
    return (module, interface) if module and interface else None


def manifest_index(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    modules: dict[str, dict[str, Any]] = {}
    interfaces: dict[str, dict[str, Any]] = {}
    for module in manifest["modules"]:
        if not isinstance(module, dict) or not isinstance(module.get("id"), str):
            continue
        module_id = module["id"]
        modules[module_id] = module
        for interface in module.get("interfaces", []):
            if isinstance(interface, dict) and isinstance(interface.get("id"), str):
                interfaces[f"{module_id}.{interface['id']}"] = interface
    return modules, interfaces


def reachable(edges: list[tuple[str, str]], source: str, destination: str) -> bool:
    queue: deque[str] = deque([source])
    seen = {source}
    while queue:
        current = queue.popleft()
        if current == destination:
            return True
        for left, right in edges:
            if left == current and right not in seen:
                seen.add(right)
                queue.append(right)
    return False


def validate(contract: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    modules, interfaces = manifest_index(manifest)
    active = contract.get("modules")
    if not isinstance(active, list) or not all(isinstance(item, str) for item in active):
        issue(errors, "contract.modules", "modules", "modules must be a list of module ids")
        active = []
    active_set = set(active)
    if len(active_set) != len(active):
        issue(errors, "contract.duplicate_module", "modules", "module list contains duplicates")
    for module_id in active_set:
        if module_id not in modules:
            issue(errors, "contract.unknown_module", "modules", f"module not in manifest: {module_id}")
        elif modules[module_id].get("state") != "reviewed":
            issue(errors, "contract.candidate_module", "modules", f"module is not reviewed: {module_id}")
    connections = contract.get("connections")
    if not isinstance(connections, list):
        issue(errors, "contract.connections", "connections", "connections must be a list")
        connections = []
    edges: list[tuple[str, str]] = []
    incoming: dict[str, list[str]] = {}
    for index, connection in enumerate(connections):
        path = f"connections[{index}]"
        if not isinstance(connection, dict):
            issue(errors, "connection.object", path, "connection must be an object")
            continue
        source = connection.get("from")
        destination = connection.get("to")
        source_parts = split_ref(source)
        destination_parts = split_ref(destination)
        if not source_parts or not destination_parts:
            issue(errors, "connection.reference", path, "from and to must use module.interface")
            continue
        source_module, _ = source_parts
        destination_module, _ = destination_parts
        if source_module not in active_set or destination_module not in active_set:
            issue(errors, "connection.inactive_module", path, "connection uses module outside contract.modules")
        source_interface = interfaces.get(source)
        destination_interface = interfaces.get(destination)
        if source_interface is None or destination_interface is None:
            issue(errors, "connection.unknown_interface", path, "connection interface missing from manifest")
            continue
        if source_interface.get("direction") != "produces" or destination_interface.get("direction") != "consumes":
            issue(errors, "connection.direction", path, "connection must be produces to consumes")
        adapter = connection.get("adapter")
        if source_interface.get("type") != destination_interface.get("type"):
            if not isinstance(adapter, str) or adapter not in active_set:
                issue(errors, "connection.type_mismatch", path, "type mismatch requires active adapter module")
            elif modules.get(adapter, {}).get("origin") != "adapter":
                issue(errors, "connection.adapter_origin", f"{path}.adapter", "adapter module must have origin adapter")
        elif adapter is not None:
            issue(warnings, "connection.unneeded_adapter", f"{path}.adapter", "same-type connection normally needs no adapter")
        edges.append((source, destination))
        incoming.setdefault(destination, []).append(source)
    for destination, sources in incoming.items():
        if len(sources) > 1:
            issue(warnings, "connection.multiple_inputs", destination, "multiple inputs need explicit mux or fusion semantics")
    internal_flows = contract.get("internal_flows", [])
    if not isinstance(internal_flows, list):
        issue(errors, "internal_flows.list", "internal_flows", "internal_flows must be a list")
        internal_flows = []
    for index, flow in enumerate(internal_flows):
        path = f"internal_flows[{index}]"
        if not isinstance(flow, dict) or not all(isinstance(flow.get(key), str) for key in ("module", "from", "to")):
            issue(errors, "internal_flow.fields", path, "module, from and to are required")
            continue
        module_id = flow["module"]
        source = f"{module_id}.{flow['from']}"
        destination = f"{module_id}.{flow['to']}"
        if module_id not in active_set:
            issue(errors, "internal_flow.inactive_module", f"{path}.module", "flow module is not active")
            continue
        source_interface = interfaces.get(source)
        destination_interface = interfaces.get(destination)
        if source_interface is None or destination_interface is None:
            issue(errors, "internal_flow.unknown_interface", path, "flow interface missing from manifest")
        elif source_interface.get("direction") != "consumes" or destination_interface.get("direction") != "produces":
            issue(errors, "internal_flow.direction", path, "internal flow must be consumes to produces")
        else:
            edges.append((source, destination))
    tf_edges = contract.get("tf_edges", [])
    if not isinstance(tf_edges, list):
        issue(errors, "tf_edges.list", "tf_edges", "tf_edges must be a list")
        tf_edges = []
    owned_edges: set[tuple[str, str]] = set()
    for index, edge in enumerate(tf_edges):
        path = f"tf_edges[{index}]"
        if not isinstance(edge, dict) or not all(isinstance(edge.get(key), str) and edge[key] for key in ("parent", "child", "owner")):
            issue(errors, "tf_edge.fields", path, "parent, child and owner are required")
            continue
        pair = (edge["parent"], edge["child"])
        if pair in owned_edges:
            issue(errors, "tf_edge.duplicate_owner", path, "dynamic TF edge has more than one owner")
        owned_edges.add(pair)
        if edge["owner"] not in active_set:
            issue(errors, "tf_edge.unknown_owner", f"{path}.owner", "TF owner is not active")
    motion_enabled = contract.get("motion_enabled", True)
    if not isinstance(motion_enabled, bool):
        issue(errors, "contract.motion_enabled", "motion_enabled", "motion_enabled must be boolean")
        motion_enabled = True
    authority = contract.get("command_authority")
    if motion_enabled:
        if not isinstance(authority, dict):
            issue(errors, "command_authority.missing", "command_authority", "motion integration requires one command authority")
        else:
            module_id = authority.get("module")
            output = authority.get("output")
            actuator = authority.get("actuator")
            if not isinstance(module_id, str) or module_id not in active_set:
                issue(errors, "command_authority.module", "command_authority.module", "authority module must be active")
            if not isinstance(output, str) or not isinstance(actuator, str):
                issue(errors, "command_authority.references", "command_authority", "output and actuator references are required")
            else:
                output_parts = split_ref(output)
                actuator_parts = split_ref(actuator)
                if not output_parts or not actuator_parts:
                    issue(errors, "command_authority.reference_format", "command_authority", "use module.interface references")
                else:
                    if output_parts[0] != module_id:
                        issue(errors, "command_authority.output_owner", "command_authority.output", "authority must own output interface")
                    if output not in interfaces or interfaces[output].get("direction") != "produces":
                        issue(errors, "command_authority.output", "command_authority.output", "output must be a produced interface")
                    if actuator not in interfaces or interfaces[actuator].get("direction") != "consumes":
                        issue(errors, "command_authority.actuator", "command_authority.actuator", "actuator must be a consumed interface")
                    if not reachable(edges, output, actuator):
                        issue(errors, "command_authority.unreachable_actuator", "command_authority", "authority output cannot reach actuator")
                    sources = authority.get("sources", [])
                    if not isinstance(sources, list) or not sources:
                        issue(errors, "command_authority.sources", "command_authority.sources", "declare at least one motion source")
                    else:
                        for source_index, source in enumerate(sources):
                            if source not in interfaces or interfaces[source].get("direction") != "produces":
                                issue(errors, "command_authority.source", f"command_authority.sources[{source_index}]", "source must be a produced interface")
                            elif not reachable(edges, source, output):
                                issue(errors, "command_authority.unreachable_source", f"command_authority.sources[{source_index}]", "motion source cannot reach authority output")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "summary": {"module_count": len(active_set), "connection_count": len(edges), "motion_enabled": motion_enabled}}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--module-manifest", required=True, type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.contract, "modules"), load_object(args.module_manifest, "modules"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
