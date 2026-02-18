from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.domain import reason_codes


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.governance
def test_every_blocked_reason_code_has_registry_schema_mapping():
    payload = json.loads((REPO_ROOT / "diagnostics" / "reason_codes.registry.json").read_text(encoding="utf-8"))
    blocked_entries = payload.get("blocked_reasons")
    assert isinstance(blocked_entries, list), "blocked_reasons must be an array"

    schema_by_code = {
        entry["code"]: entry.get("payload_schema_ref")
        for entry in blocked_entries
        if isinstance(entry, dict) and isinstance(entry.get("code"), str)
    }

    non_blocked = [
        str(entry.get("code"))
        for entry in blocked_entries
        if isinstance(entry, dict) and str(entry.get("severity", "blocked")) != "blocked"
    ]
    assert not non_blocked, f"blocked_reasons contain non-blocked severities: {non_blocked}"

    blocked_codes = sorted(code for code in reason_codes.CANONICAL_REASON_CODES if code.startswith("BLOCKED-"))
    missing = [code for code in blocked_codes if code not in schema_by_code]
    assert not missing, f"BLOCKED codes missing registry entries: {missing}"

    invalid_schema_ref: list[str] = []
    missing_schema_files: list[str] = []
    for code in blocked_codes:
        schema_ref = schema_by_code.get(code)
        if not isinstance(schema_ref, str) or not schema_ref.strip():
            invalid_schema_ref.append(code)
            continue
        schema_path = REPO_ROOT / schema_ref
        if not schema_path.exists():
            missing_schema_files.append(f"{code}:{schema_ref}")

    assert not invalid_schema_ref, f"BLOCKED codes with invalid schema refs: {invalid_schema_ref}"
    assert not missing_schema_files, f"Missing schema files for BLOCKED codes: {missing_schema_files}"


@pytest.mark.governance
def test_blocked_registry_has_exactly_one_entry_per_domain_blocked_code():
    payload = json.loads((REPO_ROOT / "diagnostics" / "reason_codes.registry.json").read_text(encoding="utf-8"))
    blocked_entries = payload.get("blocked_reasons")
    assert isinstance(blocked_entries, list), "blocked_reasons must be an array"

    domain_blocked = sorted(code for code in reason_codes.CANONICAL_REASON_CODES if code.startswith("BLOCKED-"))
    registry_codes: list[str] = [
        str(entry.get("code"))
        for entry in blocked_entries
        if isinstance(entry, dict) and isinstance(entry.get("code"), str)
    ]

    duplicates = sorted({code for code in registry_codes if registry_codes.count(code) > 1})
    assert not duplicates, f"duplicate blocked registry entries found: {duplicates}"

    registry_blocked_prefixed = sorted(code for code in registry_codes if code.startswith("BLOCKED-"))
    assert registry_blocked_prefixed == domain_blocked, (
        "blocked_reasons must include each domain BLOCKED-* reason code exactly once"
    )


@pytest.mark.governance
def test_registry_covers_all_domain_reason_codes():
    payload = json.loads((REPO_ROOT / "diagnostics" / "reason_codes.registry.json").read_text(encoding="utf-8"))
    blocked_entries = payload.get("blocked_reasons")
    audit_entries = payload.get("audit_events")
    assert isinstance(blocked_entries, list), "blocked_reasons must be an array"
    assert isinstance(audit_entries, list), "audit_events must be an array"

    registry_codes = {
        str(entry.get("code"))
        for entry in [*blocked_entries, *audit_entries]
        if isinstance(entry, dict) and isinstance(entry.get("code"), str)
    }
    domain_codes = {code for code in reason_codes.CANONICAL_REASON_CODES if code != "none"}
    missing = sorted(domain_codes - registry_codes)
    assert not missing, f"canonical reason codes missing from registry namespaces: {missing}"
