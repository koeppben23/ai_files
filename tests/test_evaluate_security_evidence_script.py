from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "evaluate_security_evidence.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


@pytest.mark.governance
def test_evaluate_security_evidence_passes_without_high_or_critical(tmp_path: Path):
    policy = {
        "schema": "governance.security-gate-policy.v1",
        "block_on_severities": ["critical", "high"],
        "fail_closed_on_scanner_error": True,
        "session_state_evidence_key": "SESSION_STATE.BuildEvidence.Security",
    }
    policy_path = tmp_path / "policy.json"
    _write_json(policy_path, policy)

    scanner_a = {
        "scanner_id": "dep-audit",
        "status": "success",
        "findings_by_severity": {"critical": 0, "high": 0, "medium": 2, "low": 1, "unknown": 0},
    }
    scanner_b = {
        "scanner_id": "codeql",
        "status": "success",
        "findings_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 1, "unknown": 0},
    }
    s1 = tmp_path / "scanner-a.json"
    s2 = tmp_path / "scanner-b.json"
    _write_json(s1, scanner_a)
    _write_json(s2, scanner_b)

    out = tmp_path / "security_summary.json"
    result = _run(["--policy", str(policy_path), "--input", str(s1), "--input", str(s2), "--output", str(out)])
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert payload["blocked"] is False
    assert out.exists()


@pytest.mark.governance
def test_evaluate_security_evidence_blocks_on_high_and_scanner_failure(tmp_path: Path):
    policy = {
        "schema": "governance.security-gate-policy.v1",
        "block_on_severities": ["critical", "high"],
        "fail_closed_on_scanner_error": True,
        "session_state_evidence_key": "SESSION_STATE.BuildEvidence.Security",
    }
    policy_path = tmp_path / "policy.json"
    _write_json(policy_path, policy)

    scanner_a = {
        "scanner_id": "gitleaks",
        "status": "success",
        "findings_by_severity": {"critical": 0, "high": 1, "medium": 0, "low": 0, "unknown": 0},
    }
    scanner_b = {
        "scanner_id": "workflow-hardening",
        "status": "failure",
        "findings_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0},
    }
    s1 = tmp_path / "scanner-a.json"
    s2 = tmp_path / "scanner-b.json"
    _write_json(s1, scanner_a)
    _write_json(s2, scanner_b)

    out = tmp_path / "security_summary.json"
    result = _run(["--policy", str(policy_path), "--input", str(s1), "--input", str(s2), "--output", str(out)])
    assert result.returncode == 1

    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["blocked"] is True
    reasons = "\n".join(payload["blocked_reasons"])
    assert "BLOCKED-SECURITY-SEVERITY" in reasons
    assert "BLOCKED-SCANNER-STATUS" in reasons
    assert out.exists()
