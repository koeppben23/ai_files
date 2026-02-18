#!/usr/bin/env python3

"""Bridge raw /audit reason keys to canonical governance reason codes.

This script remains behavior-compatible with existing Wave A diagnostics while
loading defaults from the central reason-code registry.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from governance.engine.reason_codes import DEFAULT_UNMAPPED_AUDIT_REASON

LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON = "WARN-UNMAPPED-AUDIT-REASON"

if DEFAULT_UNMAPPED_AUDIT_REASON != LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON:
    raise RuntimeError("reason code registry drift: default_unmapped must remain parity-compatible")


def _extract_reason_keys(report: dict[str, Any]) -> list[str]:
    """Extract ordered unique reason keys from known audit-report sections."""

    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            key = value.strip()
            if key not in seen:
                seen.add(key)
                ordered.append(key)

    status = report.get("status")
    if isinstance(status, dict):
        reason_keys = status.get("reasonKeys")
        if isinstance(reason_keys, list):
            for key in reason_keys:
                add(key)

    gate_trace = report.get("gateTrace")
    if isinstance(gate_trace, dict):
        blocking = gate_trace.get("blockingGates")
        if isinstance(blocking, list):
            for item in blocking:
                if isinstance(item, dict):
                    add(item.get("blockingReasonKey"))

    evidence = report.get("evidence")
    if isinstance(evidence, dict):
        missing_required = evidence.get("missingRequired")
        if isinstance(missing_required, list):
            for item in missing_required:
                if isinstance(item, dict):
                    add(item.get("reasonKey"))

    scope_inputs = report.get("scopeInputs")
    if isinstance(scope_inputs, dict):
        missing_required = scope_inputs.get("missingRequired")
        if isinstance(missing_required, list):
            for item in missing_required:
                if isinstance(item, dict):
                    add(item.get("reasonKey"))

    config_paths = report.get("configPaths")
    if isinstance(config_paths, dict):
        violations = config_paths.get("violations")
        if isinstance(violations, list):
            for item in violations:
                if isinstance(item, dict):
                    add(item.get("reasonKey"))

    rule_resolution = report.get("ruleResolution")
    if isinstance(rule_resolution, dict):
        errors = rule_resolution.get("errors")
        if isinstance(errors, list):
            for item in errors:
                if isinstance(item, dict):
                    add(item.get("errorKey"))

    return ordered


def _severity_rank(code: str) -> int:
    """Return deterministic severity rank used to derive primaryReasonCode."""

    if code.startswith("BLOCKED-"):
        return 3
    if code.startswith("WARN-"):
        return 2
    if code.startswith("NOT_VERIFIED-"):
        return 1
    return 0


def main() -> int:
    """Parse inputs, apply mapping rules, and emit canonical bridge payload."""

    parser = argparse.ArgumentParser(description="Map /audit reason keys to canonical governance reason codes.")
    parser.add_argument("--input", required=True, type=Path, help="Path to audit report JSON.")
    parser.add_argument(
        "--map",
        type=Path,
        default=SCRIPT_DIR / "AUDIT_REASON_CANONICAL_MAP.json",
        help="Path to reason mapping JSON.",
    )
    parser.add_argument(
        "--strict-unmapped",
        action="store_true",
        help="Exit non-zero if any audit reason key has no explicit mapping.",
    )
    args = parser.parse_args()

    report = json.loads(args.input.read_text(encoding="utf-8"))
    mapping_doc = json.loads(args.map.read_text(encoding="utf-8"))
    mappings = mapping_doc.get("mappings", {})
    default_unmapped = mapping_doc.get("default_unmapped", DEFAULT_UNMAPPED_AUDIT_REASON)

    if not isinstance(mappings, dict):
        print("ERROR: mappings must be an object")
        return 2
    if not isinstance(default_unmapped, str) or not default_unmapped:
        print("ERROR: default_unmapped must be a non-empty string")
        return 2

    audit_keys = _extract_reason_keys(report)
    mapped_rows: list[dict[str, str]] = []
    canonical_codes_ordered: list[str] = []
    seen_codes: set[str] = set()
    unmapped: list[str] = []

    for key in audit_keys:
        code = mappings.get(key)
        status = "mapped"
        if not isinstance(code, str) or not code:
            code = default_unmapped
            status = "unmapped"
            unmapped.append(key)
        mapped_rows.append(
            {
                "auditReasonKey": key,
                "canonicalReasonCode": code,
                "mappingStatus": status,
            }
        )
        if code not in seen_codes:
            seen_codes.add(code)
            canonical_codes_ordered.append(code)

    primary = "none"
    if canonical_codes_ordered:
        primary = max(canonical_codes_ordered, key=lambda c: (_severity_rank(c), -canonical_codes_ordered.index(c)))
    output = {
        "schema": "opencode.audit-canonical-bridge.v1",
        "auditReasonKeys": audit_keys,
        "canonicalReasonCodes": canonical_codes_ordered,
        "primaryReasonCode": primary,
        "mappings": mapped_rows,
        "unmapped": unmapped,
    }

    print(json.dumps(output, indent=2, ensure_ascii=True))

    if args.strict_unmapped and unmapped:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
