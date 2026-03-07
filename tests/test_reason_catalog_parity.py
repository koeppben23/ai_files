from __future__ import annotations

import json

from .util import REPO_ROOT


def test_reason_remediation_map_includes_p6_prerequisites_blocker() -> None:
    path = REPO_ROOT / "governance" / "assets" / "catalogs" / "REASON_REMEDIATION_MAP.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings")
    assert isinstance(mappings, dict), "REASON_REMEDIATION_MAP.json must contain mappings object"
    assert "BLOCKED-P6-PREREQUISITES-NOT-MET" in mappings, (
        "REASON_REMEDIATION_MAP.json missing BLOCKED-P6-PREREQUISITES-NOT-MET"
    )


def test_reason_remediation_map_includes_phase4_intake_blocker() -> None:
    path = REPO_ROOT / "governance" / "assets" / "catalogs" / "REASON_REMEDIATION_MAP.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings")
    assert isinstance(mappings, dict), "REASON_REMEDIATION_MAP.json must contain mappings object"
    assert "BLOCKED-P4-INTAKE-MISSING-EVIDENCE" in mappings, (
        "REASON_REMEDIATION_MAP.json missing BLOCKED-P4-INTAKE-MISSING-EVIDENCE"
    )


def test_reason_remediation_map_includes_phase5_plan_record_persist_blocker() -> None:
    path = REPO_ROOT / "governance" / "assets" / "catalogs" / "REASON_REMEDIATION_MAP.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings")
    assert isinstance(mappings, dict), "REASON_REMEDIATION_MAP.json must contain mappings object"
    assert "BLOCKED-P5-PLAN-RECORD-PERSIST" in mappings, (
        "REASON_REMEDIATION_MAP.json missing BLOCKED-P5-PLAN-RECORD-PERSIST"
    )
