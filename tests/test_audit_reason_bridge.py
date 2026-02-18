from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, run


@pytest.mark.governance
def test_audit_reason_bridge_maps_known_keys(tmp_path: Path):
    report = {
        "status": {"state": "blocked", "reasonKeys": ["BR_SCOPE_ARTIFACT_MISSING"]},
        "gateTrace": {
            "activeGates": [],
            "blockingGates": [
                {
                    "gateKey": "P5-Architecture",
                    "status": "blocked",
                    "blockingReasonKey": "BR_MISSING_RULEBOOK_RESOLUTION",
                    "required": ["rulebook evidence"],
                }
            ],
        },
        "ruleResolution": {"sources": [], "errors": []},
        "evidence": {
            "items": [],
            "missingRequired": [
                {
                    "key": "ticketGoal",
                    "requiredBy": "Phase 4",
                    "reasonKey": "BR_SCOPE_ARTIFACT_MISSING",
                }
            ],
        },
        "scopeInputs": {"items": [], "missingRequired": []},
        "configPaths": {"applicability": "not-applicable", "checks": [], "violations": []},
        "confidence": {"ceiling": 0, "reasons": ["missing state"], "blockedConfidence": True},
        "allowedNextActions": [
            {"action": "Provide evidence", "type": "provide-evidence", "unblocks": ["P5-Architecture"]}
        ],
        "phase": {"current": "1.5", "degraded": "inactive", "confidence": 0},
        "meta": {"timestamp": "2026-02-09T00:00:00Z", "mode": "repo-aware", "generator": "test", "schemaVersion": "1.0"},
    }

    inp = tmp_path / "audit.json"
    inp.write_text(json.dumps(report), encoding="utf-8")
    script = REPO_ROOT / "diagnostics" / "map_audit_to_canonical.py"

    r = run([sys.executable, str(script), "--input", str(inp)])
    assert r.returncode == 0, f"bridge failed:\n{r.stdout}\n{r.stderr}"
    out = json.loads(r.stdout)
    assert out["primaryReasonCode"] == "BLOCKED-MISSING-EVIDENCE"
    assert "BLOCKED-RULEBOOK-EVIDENCE-MISSING" in out["canonicalReasonCodes"]
    assert out["unmapped"] == []


@pytest.mark.governance
def test_audit_reason_bridge_strict_unmapped_fails(tmp_path: Path):
    report = {
        "status": {"state": "blocked", "reasonKeys": ["BR_UNKNOWN_NEW_KEY"]},
        "gateTrace": {"activeGates": [], "blockingGates": []},
        "ruleResolution": {"sources": [], "errors": []},
        "evidence": {"items": [], "missingRequired": []},
        "scopeInputs": {"items": [], "missingRequired": []},
        "configPaths": {"applicability": "not-applicable", "checks": [], "violations": []},
        "confidence": {"ceiling": 0, "reasons": [], "blockedConfidence": False},
        "allowedNextActions": [
            {"action": "Provide evidence", "type": "provide-evidence", "unblocks": []}
        ],
        "phase": {"current": "1.5", "degraded": "inactive", "confidence": 0},
        "meta": {"timestamp": "2026-02-09T00:00:00Z", "mode": "repo-aware", "generator": "test", "schemaVersion": "1.0"},
    }
    inp = tmp_path / "audit.json"
    inp.write_text(json.dumps(report), encoding="utf-8")
    script = REPO_ROOT / "diagnostics" / "map_audit_to_canonical.py"

    r = run([sys.executable, str(script), "--input", str(inp), "--strict-unmapped"])
    assert r.returncode == 3
    out = json.loads(r.stdout)
    assert out["canonicalReasonCodes"] == ["WARN-UNMAPPED-AUDIT-REASON"]
    assert out["unmapped"] == ["BR_UNKNOWN_NEW_KEY"]


@pytest.mark.governance
def test_audit_reason_bridge_primary_reason_prefers_higher_severity(tmp_path: Path):
    report = {
        "status": {"state": "blocked", "reasonKeys": ["BR_UNKNOWN_NEW_KEY", "BR_SCOPE_ARTIFACT_MISSING"]},
        "gateTrace": {"activeGates": [], "blockingGates": []},
        "ruleResolution": {"sources": [], "errors": []},
        "evidence": {"items": [], "missingRequired": []},
        "scopeInputs": {"items": [], "missingRequired": []},
        "configPaths": {"applicability": "not-applicable", "checks": [], "violations": []},
        "confidence": {"ceiling": 0, "reasons": [], "blockedConfidence": False},
        "allowedNextActions": [
            {"action": "Provide evidence", "type": "provide-evidence", "unblocks": []}
        ],
        "phase": {"current": "1.5", "degraded": "inactive", "confidence": 0},
        "meta": {"timestamp": "2026-02-09T00:00:00Z", "mode": "repo-aware", "generator": "test", "schemaVersion": "1.0"},
    }
    inp = tmp_path / "audit.json"
    inp.write_text(json.dumps(report), encoding="utf-8")
    script = REPO_ROOT / "diagnostics" / "map_audit_to_canonical.py"

    r = run([sys.executable, str(script), "--input", str(inp)])
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "WARN-UNMAPPED-AUDIT-REASON" in out["canonicalReasonCodes"]
    assert "BLOCKED-MISSING-EVIDENCE" in out["canonicalReasonCodes"]
    assert out["primaryReasonCode"] == "BLOCKED-MISSING-EVIDENCE"
