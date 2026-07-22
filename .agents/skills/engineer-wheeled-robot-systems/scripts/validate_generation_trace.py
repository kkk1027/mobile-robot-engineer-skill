#!/usr/bin/env python3
"""Verify that every intake fact has an explicit, evidence-backed disposition."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DISPOSITIONS = {"used", "question", "blocked", "intentionally_unused", "overridden"}
UNSAFE_PROVENANCE = re.compile(r"(?:test_default|test_assumption|unresolved|conflict)", re.I)
SECRET_KEY = re.compile(r"(?:password|passwd|token|secret|api[_-]?key|private[_-]?key)", re.I)
SAFE_UNRESOLVED_SCOPES = {"simulation_only", "bench_only", "documentation_only", "blocked_real"}


@dataclass(frozen=True)
class Fact:
    path: str
    provenance: str | None


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def iter_facts(value: Any, path: str = "", provenance: str | None = None) -> Iterable[Fact]:
    if isinstance(value, dict):
        local = str(value.get("provenance")) if value.get("provenance") is not None else provenance
        if "value" in value:
            yield Fact(path, local)
            return
        for key, child in value.items():
            if key == "provenance" or SECRET_KEY.search(str(key)):
                continue
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_facts(child, child_path, local)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_facts(child, f"{path}[{index}]", provenance)
        return
    yield Fact(path, provenance)


def validate(intake_path: Path, trace: dict[str, Any], project_root: Path | None) -> dict[str, Any]:
    intake = load_object(intake_path)
    allowed = intake.get("allowed_input", intake)
    if not isinstance(allowed, dict):
        raise ValueError("allowed_input must be a JSON object")
    facts = {fact.path: fact for fact in iter_facts(allowed) if fact.path}
    traced = trace.get("facts")
    if not isinstance(traced, dict):
        raise ValueError("trace.facts must be a JSON object keyed by intake path")

    issues: list[dict[str, str]] = []
    expected_hash = hashlib.sha256(intake_path.read_bytes()).hexdigest()
    if trace.get("intake_sha256") != expected_hash:
        issues.append({"code": "trace.intake_hash", "path": "intake_sha256", "message": "trace does not bind to this intake file"})
    for path, fact in facts.items():
        record = traced.get(path)
        if not isinstance(record, dict):
            issues.append({"code": "trace.missing_fact", "path": path, "message": "input fact has no disposition"})
            continue
        disposition = record.get("disposition")
        if disposition not in DISPOSITIONS:
            issues.append({"code": "trace.disposition", "path": path, "message": "invalid disposition"})
            continue
        if disposition in {"used", "overridden"}:
            evidence = record.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                issues.append({"code": "trace.used_evidence", "path": path, "message": "used fact needs generated-file evidence"})
            elif project_root is not None:
                for item in evidence:
                    if not isinstance(item, str) or Path(item).is_absolute() or not (project_root / item.split("#", 1)[0]).is_file():
                        issues.append({"code": "trace.evidence_path", "path": path, "message": f"missing or unsafe evidence path: {item}"})
            if fact.provenance and UNSAFE_PROVENANCE.search(fact.provenance):
                if record.get("scope") not in SAFE_UNRESOLVED_SCOPES:
                    issues.append({"code": "trace.unsafe_scope", "path": path, "message": "unsafe provenance used without a non-real scope"})
            if disposition == "overridden":
                authorization = record.get("authorization")
                if not isinstance(authorization, dict) or authorization.get("kind") != "user_explicit" or not str(authorization.get("record", "")).strip():
                    issues.append({"code": "trace.override_authorization", "path": path, "message": "overridden fact needs an explicit user authorization record"})
                for key in ("reason", "replacement", "impact"):
                    if not str(record.get(key, "")).strip():
                        issues.append({"code": f"trace.override_{key}", "path": path, "message": f"overridden fact needs {key}"})
        elif disposition == "question" and not str(record.get("question", "")).strip():
            issues.append({"code": "trace.question", "path": path, "message": "question disposition needs a question"})
        elif disposition in {"blocked", "intentionally_unused"} and not str(record.get("reason", "")).strip():
            issues.append({"code": "trace.reason", "path": path, "message": f"{disposition} disposition needs a reason"})

    extras = sorted(set(traced) - set(facts))
    counts = {name: 0 for name in sorted(DISPOSITIONS)}
    for path in facts:
        record = traced.get(path)
        if isinstance(record, dict) and record.get("disposition") in counts:
            counts[record["disposition"]] += 1
    return {
        "schema_version": 1,
        "ok": not issues,
        "fact_count": len(facts),
        "traced_fact_count": sum(counts.values()),
        "disposition_counts": counts,
        "extra_trace_paths": extras,
        "issues": issues,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intake", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        intake_path = args.intake.resolve()
        trace = load_object(args.trace.resolve())
        project_root = args.project_root.resolve() if args.project_root else None
        result = validate(intake_path, trace, project_root)
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
