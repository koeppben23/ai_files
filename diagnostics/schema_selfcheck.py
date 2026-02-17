#!/usr/bin/env python3
"""Deterministic selfcheck for reason registry and payload schemas.

This helper verifies that diagnostics/reason_codes.registry.json exists,
matches expected schema tag, and all referenced payload schemas are present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "diagnostics" / "reason_codes.registry.json"
EXPECTED_SCHEMA = "governance.reason-codes.registry.v1"


def main() -> int:
    if not REGISTRY_PATH.exists():
        print(f"BLOCKED: reason schema registry missing: {REGISTRY_PATH}")
        return 2

    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parse path
        print(f"BLOCKED: reason schema registry unreadable: {exc}")
        return 2

    if not isinstance(payload, dict):
        print("BLOCKED: reason schema registry must be a JSON object")
        return 2

    if payload.get("schema") != EXPECTED_SCHEMA:
        print(
            "BLOCKED: reason schema registry schema mismatch: "
            f"expected {EXPECTED_SCHEMA}, got {payload.get('schema')!r}"
        )
        return 2

    codes = payload.get("codes")
    if not isinstance(codes, list):
        print("BLOCKED: reason schema registry 'codes' must be an array")
        return 2

    missing: list[str] = []
    for entry in codes:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        schema_ref = entry.get("payload_schema_ref")
        if not isinstance(code, str) or not isinstance(schema_ref, str):
            continue
        schema_path = REPO_ROOT / schema_ref
        if not schema_path.exists():
            missing.append(f"{code}: {schema_ref}")

    if missing:
        print("BLOCKED: missing reason payload schemas:")
        for item in missing:
            print(f"- {item}")
        return 2

    print("OK: reason schema registry and payload schemas present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
