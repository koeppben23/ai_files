from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governance.engine import reason_codes
from .util import REPO_ROOT, run


@pytest.mark.governance
def test_reason_code_registry_contains_wave_a_baseline_codes():
    """Registry must expose the Wave A baseline reason codes without duplicates."""

    assert reason_codes.BLOCKED_MISSING_BINDING_FILE in reason_codes.CANONICAL_REASON_CODES
    assert reason_codes.BLOCKED_VARIABLE_RESOLUTION in reason_codes.CANONICAL_REASON_CODES
    assert reason_codes.BLOCKED_WORKSPACE_PERSISTENCE in reason_codes.CANONICAL_REASON_CODES
    assert reason_codes.WARN_UNMAPPED_AUDIT_REASON in reason_codes.CANONICAL_REASON_CODES
    assert reason_codes.WARN_WORKSPACE_PERSISTENCE in reason_codes.CANONICAL_REASON_CODES
    assert len(reason_codes.CANONICAL_REASON_CODES) == len(set(reason_codes.CANONICAL_REASON_CODES))


@pytest.mark.governance
def test_map_audit_bridge_uses_registry_default_when_map_omits_default(tmp_path: Path):
    """Bridge should use registry default when mapping file omits a fallback code."""

    report = {
        "status": {"state": "blocked", "reasonKeys": ["BR_UNKNOWN_KEY"]},
        "gateTrace": {"activeGates": [], "blockingGates": []},
        "ruleResolution": {"sources": [], "errors": []},
        "evidence": {"items": [], "missingRequired": []},
        "scopeInputs": {"items": [], "missingRequired": []},
        "configPaths": {"applicability": "not-applicable", "checks": [], "violations": []},
    }
    custom_map = {
        "$schema": "opencode.audit-reason-map.v1",
        "version": "1.0",
        "mappings": {},
    }

    report_file = tmp_path / "audit.json"
    report_file.write_text(json.dumps(report), encoding="utf-8")
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps(custom_map), encoding="utf-8")

    script = REPO_ROOT / "diagnostics" / "map_audit_to_canonical.py"
    result = run([sys.executable, str(script), "--input", str(report_file), "--map", str(map_file)])

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["canonicalReasonCodes"] == [reason_codes.WARN_UNMAPPED_AUDIT_REASON]
