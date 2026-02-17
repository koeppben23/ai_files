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
            "type": "command",
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
        "next_action": {"type": "command", "Status": "blocked", "Next": "n", "Why": "w", "Command": "cmd-c"},
        "snapshot": {"Confidence": "50%", "Risk": "LOW", "Scope": "global"},
    }
    f = tmp_path / "invalid.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "command coherence violated" in (r.stdout + r.stderr)


@pytest.mark.governance
def test_response_contract_checker_rejects_ticket_prompt_before_phase_4(tmp_path: Path):
    payload = {
        "status": "degraded",
        "session_state": {
            "Mode": "DEGRADED",
            "Phase": "2-RepoDiscovery",
            "Next": "Complete repo discovery + set working set/component scope before Phase 4 planning",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Provide the task/ticket to plan against (Phase 4 entry)",
            "Why": "Phase 4 requires a concrete goal; repo identity and profile are now established",
            "Command": "none",
        },
        "snapshot": {"Confidence": "78%", "Risk": "MEDIUM", "Scope": "global"},
    }
    f = tmp_path / "invalid_prephase4_ticket_prompt.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "must not request task/ticket input before phase 4" in (r.stdout + r.stderr)


@pytest.mark.governance
def test_response_contract_checker_allows_ticket_prompt_at_phase_4(tmp_path: Path):
    payload = {
        "status": "normal",
        "session_state": {
            "Mode": "OK",
            "Phase": "4-Implement",
            "Next": "Phase 4 entry",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Provide the task/ticket to plan against",
            "Why": "Phase 4 requires ticket goal input",
            "Command": "none",
        },
        "snapshot": {"Confidence": "85%", "Risk": "LOW", "Scope": "repo"},
    }
    f = tmp_path / "valid_phase4_ticket_prompt.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode == 0, f"validator should accept phase-4 ticket prompt:\n{r.stdout}\n{r.stderr}"


@pytest.mark.governance
def test_response_contract_checker_rejects_next_action_mismatch_with_scope_gate(tmp_path: Path):
    payload = {
        "status": "degraded",
        "session_state": {
            "Mode": "DEGRADED",
            "Phase": "2-RepoDiscovery",
            "next_gate_condition": "Complete repo discovery + set working set/component scope before Phase 4 planning",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Review details and continue",
            "Why": "Repo identity established",
            "Command": "none",
        },
        "snapshot": {"Confidence": "78%", "Risk": "MEDIUM", "Scope": "global"},
    }
    f = tmp_path / "invalid_scope_mismatch.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "next_action must align with next_gate_condition scope/working-set requirements" in (r.stdout + r.stderr)


@pytest.mark.governance
def test_response_contract_checker_accepts_scope_aligned_next_action(tmp_path: Path):
    payload = {
        "status": "degraded",
        "session_state": {
            "Mode": "DEGRADED",
            "Phase": "2-RepoDiscovery",
            "next_gate_condition": "Complete repo discovery + set working set/component scope before Phase 4 planning",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Set working set and component scope for Phase 3 entry",
            "Why": "Phase 4 planning requires scope to be locked first",
            "Command": "none",
        },
        "snapshot": {"Confidence": "78%", "Risk": "MEDIUM", "Scope": "global"},
    }
    f = tmp_path / "valid_scope_aligned.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode == 0, f"validator should accept scope-aligned next action:\n{r.stdout}\n{r.stderr}"
