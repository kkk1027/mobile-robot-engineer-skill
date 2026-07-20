"""Create a reviewable integration module manifest from a ROS source inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("inventory must be a JSON object")
    packages = value.get("packages")
    if not isinstance(packages, list):
        raise ValueError("inventory.packages must be a list")
    return value


def module_id(name: str, used: set[str]) -> str:
    candidate = "".join(char.lower() if char.isalnum() else "_" for char in name).strip("_") or "module"
    unique = candidate
    index = 2
    while unique in used:
        unique = f"{candidate}_{index}"
        index += 1
    used.add(unique)
    return unique


def create(inventory: dict[str, Any], digest: str) -> dict[str, Any]:
    used: set[str] = set()
    modules: list[dict[str, Any]] = []
    for package in inventory["packages"]:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            continue
        name = package["name"]
        modules.append({
            "id": module_id(name, used),
            "state": "candidate",
            "origin": "existing_source",
            "source_package": name,
            "source_path": package.get("path"),
            "modification_policy": "read_only",
            "maturity": "M0",
            "classification": "blocked",
            "roles": [],
            "interfaces": [],
            "dependencies": package.get("dependencies", []),
            "verification": [],
            "notes": "由清单自动生成；必须人工确认职责、接口方向、复用结论与验证证据。",
        })
    warnings = []
    if not modules:
        warnings.append(
            "清单中没有可识别的 ROS 包；当前源码范围可能缺少 package.xml/package.yaml，不能据此判断不存在可复用资产。"
        )
    return {
        "schema_version": 1,
        "source_inventory_sha256": digest,
        "source_inventory_root": inventory.get("root"),
        "modules": modules,
        "observed": {
            key: inventory.get(key, [])
            for key in ("ros", "languages", "frameworks", "base_types", "features", "package_roles")
        },
        "warnings": warnings,
        "questions": [
            "每个模块实际提供或消费哪些 ROS 接口、单位、frame 和时间语义？",
            "哪些模块允许修改，哪些必须通过适配层复用？",
            "哪些模块已独立构建或测试，哪些只是在源码中被发现？",
            "客户需求需要哪些模块、接口和集成级验收？",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="inventory JSON from inspect_ros_workspace.py")
    parser.add_argument("--output", type=Path, help="write manifest JSON")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        raw = args.inventory.read_bytes()
        manifest = create(load_object(args.inventory), hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    text = json.dumps(manifest, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
