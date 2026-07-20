"""Validate customer requirement traceability for an integrated robot product."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PRIORITIES = {"P0", "P1", "P2", "P3"}
STATUSES = {"planned", "partial", "blocked", "complete"}
LEVELS = {"unit", "integration_sim", "bench", "hil", "field"}
INTEGRATION_LEVELS = {"integration_sim", "bench", "hil", "field"}
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


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


def strings(value: Any) -> list[str] | None:
    return value if isinstance(value, list) and all(isinstance(item, str) and item for item in value) else None


def manifest_refs(manifest: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    modules: set[str] = set()
    interfaces: set[str] = set()
    if not manifest:
        return modules, interfaces
    for module in manifest["modules"]:
        if not isinstance(module, dict) or not isinstance(module.get("id"), str):
            continue
        module_id = module["id"]
        modules.add(module_id)
        for interface in module.get("interfaces", []):
            if isinstance(interface, dict) and isinstance(interface.get("id"), str):
                interfaces.add(f"{module_id}.{interface['id']}")
    return modules, interfaces


def validate(trace: dict[str, Any], manifest: dict[str, Any] | None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    known_modules, known_interfaces = manifest_refs(manifest)
    seen: set[str] = set()
    complete = 0
    by_priority = {priority: 0 for priority in PRIORITIES}
    for index, requirement in enumerate(trace["requirements"]):
        path = f"requirements[{index}]"
        if not isinstance(requirement, dict):
            issue(errors, "requirement.object", path, "requirement must be an object")
            continue
        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str) or not ID.fullmatch(requirement_id):
            issue(errors, "requirement.id", f"{path}.id", "requirement id is invalid")
            continue
        if requirement_id in seen:
            issue(errors, "requirement.duplicate_id", f"{path}.id", "requirement id must be unique")
        seen.add(requirement_id)
        priority = requirement.get("priority")
        status = requirement.get("status")
        if priority not in PRIORITIES:
            issue(errors, "requirement.priority", f"{path}.priority", "priority must be P0 through P3")
        else:
            by_priority[priority] += 1
        if status not in STATUSES:
            issue(errors, "requirement.status", f"{path}.status", "status is invalid")
            continue
        if status == "complete":
            complete += 1
        module_refs = strings(requirement.get("module_refs")) or []
        interface_refs = strings(requirement.get("interface_refs")) or []
        verification = requirement.get("verification")
        if status in {"partial", "complete"} and not module_refs:
            issue(errors, "requirement.modules", f"{path}.module_refs", "partial or complete requirement needs module references")
        if status == "complete" and not interface_refs:
            issue(errors, "requirement.interfaces", f"{path}.interface_refs", "complete requirement needs interface references")
        if status == "blocked" and not isinstance(requirement.get("reason"), str):
            issue(errors, "requirement.blocked_reason", f"{path}.reason", "blocked requirement needs a reason")
        for ref_index, module_id in enumerate(module_refs):
            if manifest and module_id not in known_modules:
                issue(errors, "requirement.unknown_module", f"{path}.module_refs[{ref_index}]", "module ref is missing from manifest")
        for ref_index, interface_id in enumerate(interface_refs):
            if manifest and interface_id not in known_interfaces:
                issue(errors, "requirement.unknown_interface", f"{path}.interface_refs[{ref_index}]", "interface ref is missing from manifest")
        if not isinstance(verification, list):
            issue(errors, "requirement.verification", f"{path}.verification", "verification must be a list")
            verification = []
        passed: list[dict[str, Any]] = []
        for verify_index, check in enumerate(verification):
            verify_path = f"{path}.verification[{verify_index}]"
            if not isinstance(check, dict) or not isinstance(check.get("id"), str):
                issue(errors, "verification.object", verify_path, "verification id is required")
                continue
            if check.get("level") not in LEVELS:
                issue(errors, "verification.level", f"{verify_path}.level", "invalid verification level")
            if check.get("status") == "passed":
                evidence = strings(check.get("evidence"))
                if not evidence:
                    issue(errors, "verification.evidence", f"{verify_path}.evidence", "passed verification needs evidence")
                else:
                    passed.append(check)
        if status == "complete" and not passed:
            issue(errors, "requirement.complete_evidence", path, "complete requirement needs passed verification with evidence")
        if status == "complete" and priority in {"P0", "P1"} and not any(check.get("level") in INTEGRATION_LEVELS for check in passed):
            issue(errors, "requirement.integration_evidence", path, "complete P0/P1 requirement needs integration, bench, HIL or field evidence")
        if status == "complete" and priority in {"P0", "P1"} and not manifest:
            issue(warnings, "requirement.unchecked_refs", path, "provide --module-manifest to validate module and interface references")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "summary": {"requirement_count": len(trace["requirements"]), "complete_count": complete, "by_priority": by_priority}}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--module-manifest", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        manifest = load_object(args.module_manifest, "modules") if args.module_manifest else None
        result = validate(load_object(args.trace, "requirements"), manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
