#!/usr/bin/env python3
"""Compare a proposed robot solution with a static repository inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FIELDS = ("ros", "languages", "frameworks", "packages", "package_roles", "interfaces", "features")
SEMANTIC_FIELDS = tuple(field for field in FIELDS if field != "packages")
SAFETY_FEATURES = {"command_timeout", "emergency_stop", "watchdog", "command_arbitration"}
FRAMEWORK_ALIASES = {
    "ydlidar_ros2_driver": {"ydlidar"},
    "flask_socketio": {"flask", "socketio"},
    "yolov8": {"yolo"},
    "yolov8n": {"yolo"},
}
FEATURE_ALIASES = {
    "slam": {"mapping"},
    "known_map_navigation": {"navigation"},
    "waypoint_patrol": {"patrol"},
    "optional_human_following": {"human_following"},
}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def normalize_value(value: Any, field: str | None = None) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if field == "interfaces" and normalized:
        normalized = "/" + normalized.lstrip("/")
    return normalized


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
        output.add(normalize_value(item, field))
    return output


def interface_role(value: str) -> str:
    bare = value.lstrip("/")
    if "cmd_vel" in bare or "twist" in bare:
        return "motion_command"
    if "emergency_stop" in bare or "e_stop" in bare:
        return "emergency_stop"
    if "diagnostic" in bare or "health" in bare:
        return "diagnostics"
    if "tf_static" in bare:
        return "tf_static"
    if bare == "tf" or bare.endswith("/tf"):
        return "tf"
    if "odom" in bare:
        return "odometry"
    if "imu" in bare:
        return "imu"
    if "scan" in bare or "laser" in bare:
        return "laser_scan"
    if bare == "map" or bare.endswith("/map"):
        return "map"
    if "mode" in bare:
        return "operating_mode"
    return value


def semantic_list(value: Any, field: str) -> set[str]:
    literal = normalize_list(value, field)
    output: set[str] = set()
    for item in literal:
        if field == "frameworks":
            output.update(FRAMEWORK_ALIASES.get(item, {item}))
        elif field == "features":
            output.update(FEATURE_ALIASES.get(item, {item}))
        elif field == "interfaces":
            output.add(interface_role(item))
        else:
            output.add(item)
    return output


def evidence_for(inventory: dict[str, Any], field: str, value: str) -> list[dict[str, Any]]:
    evidence = inventory.get("evidence", {})
    if not isinstance(evidence, dict):
        return []
    category = evidence.get(field, {})
    if not isinstance(category, dict):
        return []
    for raw_key, hits in category.items():
        if normalize_value(raw_key, field) == value and isinstance(hits, list):
            return hits
    return []


def compare(solution: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    semantic_comparisons: dict[str, Any] = {}
    exact_expected = 0
    exact_matched = 0
    semantic_expected = 0
    semantic_matched = 0
    for field in FIELDS:
        expected = normalize_list(solution.get(field, []), field)
        actual = normalize_list(inventory.get(field, []), field)
        matched = sorted(expected & actual)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        exact_expected += len(expected)
        exact_matched += len(matched)
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

    for field in SEMANTIC_FIELDS:
        expected = semantic_list(solution.get(field, []), field)
        actual = semantic_list(inventory.get(field, []), field)
        matched = sorted(expected & actual)
        semantic_expected += len(expected)
        semantic_matched += len(matched)
        semantic_comparisons[field] = {
            "expected_roles": sorted(expected),
            "actual_roles": sorted(actual),
            "matched_roles": matched,
            "missing_static_roles": sorted(expected - actual),
            "extra_inventory_roles": sorted(actual - expected),
        }

    expected_base = normalize_value(solution.get("base_type", ""), "base_types")
    actual_bases = normalize_list(inventory.get("base_types", []), "base_types")
    base_match = bool(expected_base and expected_base in actual_bases)
    if expected_base:
        exact_expected += 1
        exact_matched += int(base_match)
        semantic_expected += 1
        semantic_matched += int(base_match)
    expected_features = normalize_list(solution.get("features", []), "features")
    safety_expected = expected_features & SAFETY_FEATURES
    safety_missing = set(comparisons["features"]["missing_static_evidence"]) & SAFETY_FEATURES
    exact_score = 1.0 if exact_expected == 0 else exact_matched / exact_expected
    semantic_score = 1.0 if semantic_expected == 0 else semantic_matched / semantic_expected
    return {
        "schema_version": 2,
        "summary": {
            "exact_expected_items": exact_expected,
            "exact_matched_items": exact_matched,
            "exact_static_match_ratio": round(exact_score, 4),
            "semantic_expected_items": semantic_expected,
            "semantic_matched_items": semantic_matched,
            "semantic_static_match_ratio": round(semantic_score, 4),
            "static_match_ratio": round(semantic_score, 4),
            "manual_review_required": True,
            "package_name_overlap_is_informational": True,
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
        "semantic_comparisons": semantic_comparisons,
        "interpretation": [
            "missing_static_evidence is not proof that the source lacks the feature",
            "extra_in_inventory is not automatically a solution error",
            "package-name overlap has zero weight in the semantic ratio",
            "interface names are projected to coarse responsibilities for the semantic ratio",
            "known framework and feature aliases are projected before semantic comparison",
            "neither static ratio is a final quality score",
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
    configure_stdio()
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
