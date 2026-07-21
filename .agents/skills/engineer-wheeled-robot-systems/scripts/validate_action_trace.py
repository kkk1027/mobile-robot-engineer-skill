#!/usr/bin/env python3
"""Validate action outcome evidence for navigation and task workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


STATUSES = {"succeeded", "canceled", "aborted", "active", "not_run"}
TERMINAL = {"succeeded", "canceled", "aborted"}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("action trace must be a JSON object")
    return value


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def evidence_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return [item.strip() for item in value]


def validate(data: dict[str, Any], require_terminal: bool) -> dict[str, Any]:
    actions = data.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("actions must be a non-empty list")
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    results: list[dict[str, str]] = []
    goal_ids: set[str] = set()
    for index, item in enumerate(actions):
        path = f"actions[{index}]"
        if not isinstance(item, dict):
            errors.append(issue("action.item", path, "action entry must be an object"))
            continue
        goal_id = str(item.get("goal_id", "")).strip()
        action = str(item.get("action", "")).strip()
        source = str(item.get("source", "")).strip()
        status = str(item.get("status", "")).strip()
        if not goal_id:
            errors.append(issue("action.goal_id", f"{path}.goal_id", "action needs a goal ID"))
        elif goal_id in goal_ids:
            errors.append(issue("action.duplicate_goal", f"{path}.goal_id", "goal ID must be unique"))
        goal_ids.add(goal_id)
        if not action:
            errors.append(issue("action.name", f"{path}.action", "action name is required"))
        if not source:
            errors.append(issue("action.source", f"{path}.source", "action source is required"))
        if status not in STATUSES:
            errors.append(issue("action.status", f"{path}.status", "status is invalid"))
            continue
        if not str(item.get("started_at", "")).strip() and status != "not_run":
            errors.append(issue("action.started_at", f"{path}.started_at", "executed action needs start time"))
        if status in TERMINAL:
            if not str(item.get("finished_at", "")).strip():
                errors.append(issue("action.finished_at", f"{path}.finished_at", "terminal action needs finish time"))
            if evidence_list(item.get("evidence")) is None:
                errors.append(issue("action.evidence", f"{path}.evidence", "terminal action needs evidence"))
        if status == "canceled" and not str(item.get("cancel_requested_by", "")).strip():
            errors.append(issue("action.cancel_source", f"{path}.cancel_requested_by", "canceled action needs cancel source"))
        if status == "aborted":
            if not str(item.get("error_code", "")).strip():
                errors.append(issue("action.error_code", f"{path}.error_code", "aborted action needs error code"))
            if not str(item.get("error_message", "")).strip():
                errors.append(issue("action.error_message", f"{path}.error_message", "aborted action needs error message"))
        if status in {"active", "not_run"}:
            warnings.append(issue("action.not_terminal", path, "action is not terminal and cannot prove task completion"))
            if require_terminal:
                errors.append(issue("action.require_terminal", path, "this validation requires terminal action states"))
        results.append({"goal_id": goal_id, "action": action, "source": source, "status": status})
    return {
        "schema_version": 1,
        "ok": not errors,
        "terminal_ready": not errors and all(item["status"] in TERMINAL for item in results),
        "actions": results,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--require-terminal", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        result = validate(load_object(args.trace.resolve()), args.require_terminal)
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
