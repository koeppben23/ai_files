from __future__ import annotations

from pathlib import Path
import json

import pytest

from diagnostics import schema_selfcheck
from governance.engine._embedded_reason_registry import EMBEDDED_REASON_CODE_TO_SCHEMA_REF
from governance.engine._embedded_reason_schemas import EMBEDDED_REASON_SCHEMAS


@pytest.mark.governance
def test_reason_payload_schema_selfcheck_passes():
    # Executes shipped selfcheck against repository diagnostics tree.
    rc = schema_selfcheck.main()
    assert rc == 0


@pytest.mark.governance
def test_reason_payload_registry_exists_at_expected_path():
    root = Path(__file__).resolve().parents[1]
    assert (root / "diagnostics" / "reason_codes.registry.json").exists()


@pytest.mark.governance
def test_embedded_reason_registry_matches_diagnostics_registry():
    root = Path(__file__).resolve().parents[1]
    registry_path = root / "diagnostics" / "reason_codes.registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    codes: list[object] = []
    if isinstance(payload.get("blocked_reasons"), list):
        codes.extend(payload.get("blocked_reasons", []))
    if isinstance(payload.get("audit_events"), list):
        codes.extend(payload.get("audit_events", []))
    if isinstance(payload.get("codes"), list):
        codes.extend(payload.get("codes", []))
    expected = {
        entry["code"]: entry["payload_schema_ref"]
        for entry in codes
        if isinstance(entry, dict)
        and isinstance(entry.get("code"), str)
        and isinstance(entry.get("payload_schema_ref"), str)
    }
    assert EMBEDDED_REASON_CODE_TO_SCHEMA_REF == expected


@pytest.mark.governance
def test_embedded_reason_schemas_cover_embedded_registry_refs():
    refs = set(EMBEDDED_REASON_CODE_TO_SCHEMA_REF.values())
    assert refs == set(EMBEDDED_REASON_SCHEMAS.keys())
