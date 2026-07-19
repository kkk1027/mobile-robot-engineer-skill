#!/usr/bin/env python3
"""Compare a proposed robot solution with a static repository inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FIELDS = ("ros", "languages", "frameworks", "packages", "interfaces", "features")
SAFETY_FEATURES = {"command_timeout", "emergency_stop", "watchdog"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def normalize_value(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def normalize_list(value: Any, field: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    output: set[str] = set()
    for item in value:
        if field == "packages" and isinstance(item, dict):
            item = item.get("name")
        if item is None:
            continue
        output.add(normalize_value(item))
    return output


def evidence_for(inventory: dict[str, Any], field: str, value: str) -> list[dict[str, Any]]:
    evidence = inventory.get("evidence", {})
    if not isinstance(evidence, dict):
        return []
    category = evidence.get(field, {})
    if not isinstance(category, dict):
        return []
    for raw_key, hits in category.items():
        if normalize_value(raw_key) == value and isinstance(hits, list):
            return hits
    return []


def compare(solution: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    total_expected = 0
    total_matched = 0
    for field in FIELDS:
        expected = normalize_list(solution.get(field, []), field)
        actual = normalize_list(inventory.get(field, []), field)
        matched = sorted(expected & actual)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        total_expected += len(expected)
        total_matched += len(matched)
        comparisons[field] = {
            "expected": sorted(expected),
            "actual": sorted(actual),
            "matched": matched,
            "missing_static_evidence": missing,
            "extra_in_inventory": extra,
            "evidence": {
                value: evidence_for(inventory, field, value)
                for value in matched
            },
        }

    expected_base = normalize_value(solution.get("base_type", ""))
    actual_bases = normalize_list(inventory.get("base_types", []), "base_types")
    base_match = bool(expected_base and expected_base in actual_bases)
    if expected_base:
        total_expected += 1
        total_matched += int(base_match)
    expected_features = normalize_list(solution.get("features", []), "features")
    safety_expected = expected_features & SAFETY_FEATURES
    safety_missing = set(comparisons["features"]["missing_static_evidence"]) & SAFETY_FEATURES
    score = 1.0 if total_expected == 0 else total_matched / total_expected
    return {
        "schema_version": 1,
        "summary": {
            "expected_items": total_expected,
            "matched_items": total_matched,
            "static_match_ratio": round(score, 4),
            "manual_review_required": True,
            "safety_expectations": sorted(safety_expected),
            "safety_missing_static_evidence": sorted(safety_missing),
        },
        "base_type": {
            "expected": expected_base or None,
            "actual": sorted(actual_bases),
            "matched": base_match,
            "evidence": evidence_for(inventory, "base_types", expected_base) if base_match else [],
        },
        "comparisons": comparisons,
        "interpretation": [
            "missing_static_evidence is not proof that the source lacks the feature",
            "extra_in_inventory is not automatically a solution error",
            "manually inspect runtime wiring, generated files, firmware, and hardware behavior",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("solution", type=Path, help="solution JSON")
    parser.add_argument("inventory", type=Path, help="inventory JSON")
    parser.add_argument("--output", type=Path, help="write comparison JSON")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        solution = load_json(args.solution.resolve())
        inventory = load_json(args.inventory.resolve())
        result = compare(solution, inventory)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
