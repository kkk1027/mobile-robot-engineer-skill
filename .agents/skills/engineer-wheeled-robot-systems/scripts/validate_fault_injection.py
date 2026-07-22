#!/usr/bin/env python3
"""Validate motion-interrupting safety fault-injection evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXECUTIONS = {"ran", "not_run"}
STATUSES = {"passed", "failed", "not_run"}
KINDS = {"emergency_stop", "command_timeout", "health_gate", "sensor_loss", "qos_loss", "tf_loss"}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fault injection trace must be a JSON object")
    return value


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def evidence_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return [item.strip() for item in value]


def nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def positive_number(value: Any) -> bool:
    return nonnegative_number(value) and value > 0


def validate(data: dict[str, Any], require_ran: bool, require_passed: bool) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile must be a JSON object")
    name = str(profile.get("name", "")).strip()
    execution = str(profile.get("execution", "")).strip()
    if not name:
        errors.append(issue("fault.profile_name", "profile.name", "profile needs a name"))
    if execution not in EXECUTIONS:
        errors.append(issue("fault.execution", "profile.execution", "execution must be ran or not_run"))
    ran = execution == "ran"
    if not ran:
        warnings.append(issue("fault.not_run", "profile.execution", "no safety fault-injection claim may be made"))
        if require_ran:
            errors.append(issue("fault.require_ran", "profile.execution", "this validation requires an observed run"))

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    seen_ids: set[str] = set()
    results: list[dict[str, str]] = []
    for index, case in enumerate(cases):
        path = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(issue("fault.case", path, "fault case must be an object"))
            continue
        case_id = str(case.get("id", "")).strip()
        kind = str(case.get("kind", "")).strip()
        status = str(case.get("status", "")).strip()
        if not case_id:
            errors.append(issue("fault.case_id", f"{path}.id", "fault case needs an ID"))
        elif case_id in seen_ids:
            errors.append(issue("fault.duplicate_case", f"{path}.id", "fault case ID must be unique"))
        seen_ids.add(case_id)
        if kind not in KINDS:
            errors.append(issue("fault.kind", f"{path}.kind", "fault kind is invalid"))
        if status not in STATUSES:
            errors.append(issue("fault.status", f"{path}.status", "fault status is invalid"))
            continue
        if status == "not_run":
            warnings.append(issue("fault.case_not_run", path, "fault case has no execution evidence"))
            if require_passed:
                errors.append(issue("fault.require_passed", path, "this validation requires every fault case to pass"))
        elif status == "failed":
            if not str(case.get("failure_reason", "")).strip():
                errors.append(issue("fault.failure_reason", f"{path}.failure_reason", "failed fault case needs a reason"))
            if require_passed:
                errors.append(issue("fault.require_passed", path, "this validation requires every fault case to pass"))
        else:
            if not ran:
                errors.append(issue("fault.passed_without_run", path, "passed fault case requires profile.execution=ran"))
            if case.get("motion_observed_before_trigger") is not True:
                errors.append(issue("fault.motion_precondition", f"{path}.motion_observed_before_trigger", "passed motion-interrupting fault needs nonzero motion before trigger"))
            if case.get("safe_stop_observed") is not True:
                errors.append(issue("fault.safe_stop", f"{path}.safe_stop_observed", "passed fault case needs observed safe stop"))
            if not nonnegative_number(case.get("stop_latency_ms")):
                errors.append(issue("fault.stop_latency", f"{path}.stop_latency_ms", "passed fault case needs nonnegative observed stop latency"))
            maximum = case.get("max_stop_latency_ms")
            if not positive_number(maximum):
                errors.append(issue("fault.max_stop_latency", f"{path}.max_stop_latency_ms", "passed fault case needs a positive stop-latency bound"))
            elif nonnegative_number(case.get("stop_latency_ms")) and case["stop_latency_ms"] > maximum:
                errors.append(issue("fault.stop_latency_exceeded", f"{path}.stop_latency_ms", "observed stop latency exceeds declared bound"))
            if evidence_list(case.get("evidence")) is None:
                errors.append(issue("fault.evidence", f"{path}.evidence", "passed fault case needs evidence"))
        results.append({"id": case_id, "kind": kind, "status": status})
    return {
        "schema_version": 1,
        "ok": not errors,
        "passed_ready": ran and not errors and all(item["status"] == "passed" for item in results),
        "profile": {"name": name, "execution": execution},
        "cases": results,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--require-ran", action="store_true")
    parser.add_argument("--require-passed", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.trace.resolve()), args.require_ran, args.require_passed)
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
