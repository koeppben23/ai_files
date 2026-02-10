from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, run


@pytest.mark.governance
def test_response_contract_checker_accepts_valid_payload(tmp_path: Path):
    payload = {
        "status": "blocked",
        "session_state": {
            "Mode": "BLOCKED",
            "Phase": "1.3",
            "Next": "BLOCKED-RULEBOOK-EVIDENCE-MISSING",
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/rules.md", "addons": {}},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/rules.md"},
        },
        "reason_payload": {
            "status": "blocked",
            "reason_code": "BLOCKED-RULEBOOK-EVIDENCE-MISSING",
            "missing_evidence": ["rules.md load evidence"],
            "recovery_steps": ["provide load evidence"],
            "next_command": "/start",
        },
        "quick_fix_commands": ["/start"],
        "next_action": {
            "Status": "blocked",
            "Next": "Provide load evidence",
            "Why": "Rulebook evidence is required before phase completion.",
            "Command": "/start",
        },
        "snapshot": {"Confidence": "88%", "Risk": "MEDIUM", "Scope": "global"},
    }
    f = tmp_path / "valid.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode == 0, f"validator failed for valid payload:\n{r.stdout}\n{r.stderr}"


@pytest.mark.governance
def test_response_contract_checker_rejects_command_coherence_violation(tmp_path: Path):
    payload = {
        "status": "blocked",
        "session_state": {"Mode": "BLOCKED", "Phase": "1.3", "Next": "BLOCKED-TEST"},
        "reason_payload": {
            "status": "blocked",
            "reason_code": "BLOCKED-TEST",
            "missing_evidence": [],
            "recovery_steps": ["step"],
            "next_command": "cmd-a",
        },
        "quick_fix_commands": ["cmd-b"],
        "next_action": {"Status": "blocked", "Next": "n", "Why": "w", "Command": "cmd-c"},
        "snapshot": {"Confidence": "50%", "Risk": "LOW", "Scope": "global"},
    }
    f = tmp_path / "invalid.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "command coherence violated" in (r.stdout + r.stderr)
