#!/usr/bin/env python3
"""Validate checksums and referenced artifact completeness for a delivery bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SHA256 = re.compile(r"^[0-9a-f]{64}$")
REFERENCE_PREFIXES = ("artifacts/", "evidence/")


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


def issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_relative(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = raw.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
        return None
    return path.as_posix()


def bundle_path(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)
    elif isinstance(value, str):
        yield value


def validate(data: dict[str, Any], root: Path, scan_paths: list[str]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("files must be a non-empty list")
    manifest_paths: set[str] = set()
    checked: list[dict[str, str]] = []
    for index, entry in enumerate(files):
        path = f"files[{index}]"
        if not isinstance(entry, dict):
            errors.append(issue("bundle.file", path, "manifest file entry must be an object"))
            continue
        relative = safe_relative(entry.get("path"))
        expected_hash = str(entry.get("sha256", "")).strip().lower()
        if relative is None:
            errors.append(issue("bundle.path", f"{path}.path", "file path must be a safe relative path"))
            continue
        if relative in manifest_paths:
            errors.append(issue("bundle.duplicate_path", f"{path}.path", "manifest file path must be unique"))
            continue
        manifest_paths.add(relative)
        if not SHA256.fullmatch(expected_hash):
            errors.append(issue("bundle.sha256", f"{path}.sha256", "file entry needs a lowercase SHA-256"))
            continue
        candidate = bundle_path(root, relative)
        if candidate is None or not candidate.is_file():
            errors.append(issue("bundle.missing_file", f"{path}.path", f"manifest file is missing: {relative}"))
            continue
        actual_hash = sha256(candidate)
        if actual_hash != expected_hash:
            errors.append(issue("bundle.hash_mismatch", f"{path}.sha256", f"checksum mismatch for {relative}"))
        checked.append({"path": relative, "sha256": actual_hash})

    referenced: set[str] = set()
    for scan in scan_paths:
        candidate = bundle_path(root, scan)
        if candidate is None or not candidate.is_file():
            errors.append(issue("bundle.scan_missing", "scan", f"scan file is missing: {scan}"))
            continue
        try:
            scanned = load_object(candidate)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(issue("bundle.scan_invalid", "scan", f"cannot parse {scan}: {exc}"))
            continue
        for raw in strings(scanned):
            normalized = safe_relative(raw)
            if normalized and normalized.startswith(REFERENCE_PREFIXES):
                referenced.add(normalized)
    for relative in sorted(referenced):
        candidate = bundle_path(root, relative)
        if candidate is None or not candidate.is_file():
            errors.append(issue("bundle.reference_missing", relative, "referenced evidence is absent from the delivery root"))
        elif relative not in manifest_paths:
            errors.append(issue("bundle.reference_unlisted", relative, "referenced evidence is not covered by the manifest"))

    return {
        "schema_version": 1,
        "ok": not errors,
        "checked_files": checked,
        "referenced_paths": sorted(referenced),
        "errors": errors,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scan", action="append", default=[], help="relative JSON evidence file to scan; repeat as needed")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        root = args.root.resolve()
        result = validate(load_object(args.manifest.resolve()), root, args.scan)
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
