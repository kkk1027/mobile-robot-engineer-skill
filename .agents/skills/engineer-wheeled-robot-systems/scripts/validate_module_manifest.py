"""Validate a ROS module asset manifest for product integration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ORIGINS = {"existing_source", "new_driver", "new_capability", "adapter", "product_bringup"}
POLICIES = {"read_only", "adapter_only", "owned"}
MATURITY = {f"M{index}" for index in range(6)}
CLASSIFICATIONS = {"reusable", "needs_adapter", "needs_implementation", "blocked"}
STATES = {"candidate", "reviewed"}
DIRECTIONS = {"produces", "consumes"}
VERIFY_KINDS = {"build", "unit", "bench_or_fake", "integration_sim", "hil", "field", "safety_default"}
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("modules"), list):
        raise ValueError("manifest.modules must be a list")
    return value


def issue(items: list[dict[str, str]], code: str, path: str, message: str) -> None:
    items.append({"code": code, "path": path, "message": message})


def strings(value: Any) -> list[str] | None:
    return value if isinstance(value, list) and all(isinstance(item, str) and item for item in value) else None


def validate(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    modules = manifest["modules"]
    ids: set[str] = set()
    reviewed = 0
    classifications: dict[str, int] = {value: 0 for value in CLASSIFICATIONS}
    if not modules:
        issue(warnings, "manifest.empty", "modules", "no modules were identified; expand the authorized source scope before judging reuse readiness")
    for index, module in enumerate(modules):
        path = f"modules[{index}]"
        if not isinstance(module, dict):
            issue(errors, "module.object", path, "module must be an object")
            continue
        module_id = module.get("id")
        if not isinstance(module_id, str) or not ID.fullmatch(module_id):
            issue(errors, "module.id", f"{path}.id", "id must be a unique identifier")
            continue
        if module_id in ids:
            issue(errors, "module.duplicate_id", f"{path}.id", f"duplicate id: {module_id}")
        ids.add(module_id)
        state = module.get("state", "reviewed")
        if state not in STATES:
            issue(errors, "module.state", f"{path}.state", "state must be candidate or reviewed")
            continue
        if state == "candidate":
            issue(warnings, "module.candidate", path, "candidate module cannot be claimed integrated")
        else:
            reviewed += 1
        origin = module.get("origin")
        if origin not in ORIGINS:
            issue(errors, "module.origin", f"{path}.origin", f"origin must be one of {sorted(ORIGINS)}")
        policy = module.get("modification_policy")
        if policy not in POLICIES:
            issue(errors, "module.modification_policy", f"{path}.modification_policy", f"policy must be one of {sorted(POLICIES)}")
        maturity = module.get("maturity")
        if maturity not in MATURITY:
            issue(errors, "module.maturity", f"{path}.maturity", "maturity must be M0 through M5")
        classification = module.get("classification")
        if classification not in CLASSIFICATIONS:
            issue(errors, "module.classification", f"{path}.classification", "invalid reuse classification")
        else:
            classifications[classification] += 1
        roles = strings(module.get("roles"))
        interfaces = module.get("interfaces")
        verification = module.get("verification")
        if state == "reviewed" and classification != "blocked" and not roles:
            issue(errors, "module.roles", f"{path}.roles", "reviewed usable module needs at least one role")
        if not isinstance(interfaces, list):
            issue(errors, "module.interfaces", f"{path}.interfaces", "interfaces must be a list")
            interfaces = []
        interface_ids: set[str] = set()
        for interface_index, interface in enumerate(interfaces):
            interface_path = f"{path}.interfaces[{interface_index}]"
            if not isinstance(interface, dict):
                issue(errors, "interface.object", interface_path, "interface must be an object")
                continue
            interface_id = interface.get("id")
            if not isinstance(interface_id, str) or not ID.fullmatch(interface_id):
                issue(errors, "interface.id", f"{interface_path}.id", "interface id is invalid")
            elif interface_id in interface_ids:
                issue(errors, "interface.duplicate_id", f"{interface_path}.id", "duplicate interface id in module")
            else:
                interface_ids.add(interface_id)
            if not isinstance(interface.get("name"), str) or not interface["name"]:
                issue(errors, "interface.name", f"{interface_path}.name", "interface name is required")
            if not isinstance(interface.get("type"), str) or not interface["type"]:
                issue(errors, "interface.type", f"{interface_path}.type", "ROS type is required")
            if interface.get("direction") not in DIRECTIONS:
                issue(errors, "interface.direction", f"{interface_path}.direction", "direction must be produces or consumes")
        if not isinstance(verification, list):
            issue(errors, "module.verification", f"{path}.verification", "verification must be a list")
            verification = []
        kinds: set[str] = set()
        for verify_index, check in enumerate(verification):
            verify_path = f"{path}.verification[{verify_index}]"
            if not isinstance(check, dict) or check.get("kind") not in VERIFY_KINDS:
                issue(errors, "verification.kind", verify_path, "verification kind is invalid")
                continue
            kinds.add(check["kind"])
            evidence = strings(check.get("evidence"))
            if state == "reviewed" and classification != "blocked" and not evidence:
                issue(errors, "verification.evidence", f"{verify_path}.evidence", "reviewed verification needs evidence")
        if state == "reviewed" and classification == "reusable" and not verification:
            issue(errors, "module.reusable_evidence", path, "reusable module needs verification evidence")
        if state == "reviewed" and origin == "new_driver" and classification != "blocked":
            required = {"build", "bench_or_fake", "safety_default"}
            missing = sorted(required - kinds)
            if missing:
                issue(errors, "driver.baseline", path, f"new_driver lacks required verification: {', '.join(missing)}")
            if not interfaces:
                issue(errors, "driver.interfaces", path, "new_driver needs stable ROS interfaces")
        if state == "reviewed" and origin == "adapter" and policy == "read_only":
            issue(errors, "adapter.policy", f"{path}.modification_policy", "adapter must be adapter_only or owned")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {"module_count": len(modules), "reviewed_count": reviewed, "classifications": classifications},
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
