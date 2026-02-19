#!/usr/bin/env python3
"""Validate SESSION_STATE files against schema and invariants.

This script is intended for CI integration to catch SESSION_STATE drift.
It validates all SESSION_STATE.json files found under workspaces directories.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance.engine.schema_validator import validate_against_schema
from governance.engine._embedded_session_state_schema import SESSION_STATE_CORE_SCHEMA
from governance.engine.session_state_invariants import validate_session_state_invariants


def find_session_state_files(repo_root: Path) -> list[Path]:
    """Find all SESSION_STATE.json files under workspaces directories."""
    files = []
    for pattern in ["**/SESSION_STATE.json", "**/session_state.json"]:
        files.extend(repo_root.glob(pattern))
    return sorted(set(files))


def validate_file(path: Path) -> tuple[bool, list[str]]:
    """Validate a single SESSION_STATE file. Returns (valid, errors)."""
    errors = []

    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"JSON parse error: {e}"]

    if not isinstance(doc, dict):
        return False, ["Document must be a JSON object"]

    # Schema validation
    schema_errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
    for err in schema_errors:
        errors.append(f"Schema: {err}")

    # Invariant validation
    invariant_errors = validate_session_state_invariants(doc)
    for err in invariant_errors:
        errors.append(f"Invariant: {err}")

    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SESSION_STATE files")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--files", nargs="*", type=Path, help="Specific files to validate (default: auto-discover)")
    parser.add_argument("--quiet", action="store_true", help="Only print errors")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()

    if args.files:
        files = [f if f.is_absolute() else repo_root / f for f in args.files]
    else:
        files = find_session_state_files(repo_root)

    if not files:
        if not args.quiet:
            print("No SESSION_STATE files found")
        return 0

    total_errors = 0
    for path in files:
        rel_path = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        valid, errors = validate_file(path)

        if valid:
            if not args.quiet:
                print(f"OK: {rel_path}")
        else:
            print(f"FAIL: {rel_path}")
            for err in errors:
                print(f"  - {err}")
            total_errors += len(errors)

    if total_errors > 0:
        print(f"\nTotal errors: {total_errors}")
        return 1

    if not args.quiet:
        print(f"\nAll {len(files)} SESSION_STATE files valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
