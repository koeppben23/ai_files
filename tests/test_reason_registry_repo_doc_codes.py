from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _registry_entries(payload: dict[str, object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for key in ("blocked_reasons", "audit_events", "codes"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        out.extend(entry for entry in value if isinstance(entry, dict))
    return out


def test_reason_registry_includes_mode_aware_repo_doc_codes():
    registry_path = REPO_ROOT / "diagnostics" / "reason_codes.registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    codes = {str(entry.get("code")) for entry in _registry_entries(payload)}
    required = {
        "REPO-DOC-UNSAFE-DIRECTIVE",
        "REPO-CONSTRAINT-WIDENING",
        "INTERACTIVE-REQUIRED-IN-PIPELINE",
        "PROMPT-BUDGET-EXCEEDED",
        "REPO-CONSTRAINT-UNSUPPORTED",
        "POLICY-PRECEDENCE-APPLIED",
    }
    assert required.issubset(codes)


def test_reason_registry_payload_schema_refs_exist():
    registry_path = REPO_ROOT / "diagnostics" / "reason_codes.registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    for entry in _registry_entries(payload):
        schema_ref = entry.get("payload_schema_ref")
        if not isinstance(schema_ref, str) or not schema_ref:
            continue
        schema_path = REPO_ROOT / schema_ref
        assert schema_path.exists(), f"Missing schema file for {entry.get('code')}: {schema_ref}"
