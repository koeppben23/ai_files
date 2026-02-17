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


@pytest.mark.governance
def test_response_contract_checker_rejects_phase_3a_next_action_without_3b_progression(tmp_path: Path):
    payload = {
        "status": "normal",
        "session_state": {
            "Mode": "OK",
            "Phase": "3A",
            "next_gate_condition": "Proceed to Phase 3B-1",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Summarize repository findings",
            "Why": "Discovery complete",
            "Command": "none",
        },
        "snapshot": {"Confidence": "80%", "Risk": "LOW", "Scope": "repo"},
    }
    f = tmp_path / "invalid_3a_next_action.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "next_action must align with phase 3A progression semantics" in (r.stdout + r.stderr)


@pytest.mark.governance
def test_response_contract_checker_accepts_phase_3a_next_action_with_3b_progression(tmp_path: Path):
    payload = {
        "status": "normal",
        "session_state": {
            "Mode": "OK",
            "Phase": "3A",
            "next_gate_condition": "Proceed to Phase 3B-1",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Proceed to Phase 3B-1 API logical validation",
            "Why": "Phase 3A exits to 3B-1",
            "Command": "none",
        },
        "snapshot": {"Confidence": "80%", "Risk": "LOW", "Scope": "repo"},
    }
    f = tmp_path / "valid_3a_next_action.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode == 0, f"validator should accept phase-3A progression:\n{r.stdout}\n{r.stderr}"


@pytest.mark.governance
def test_response_contract_checker_rejects_phase_15_without_phase_21_predecessor(tmp_path: Path):
    payload = {
        "status": "degraded",
        "session_state": {
            "Mode": "DEGRADED",
            "Phase": "1.5-BusinessRules",
            "previous_phase": "2-RepoDiscovery",
            "next_gate_condition": "Proceed to Phase 3A",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Proceed to Phase 3A API inventory",
            "Why": "Business rules extraction complete",
            "Command": "none",
        },
        "snapshot": {"Confidence": "75%", "Risk": "MEDIUM", "Scope": "repo"},
    }
    f = tmp_path / "invalid_15_predecessor.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "phase 1.5 may only follow phase 2.1 or explicit later-phase reopen" in (r.stdout + r.stderr)


@pytest.mark.governance
def test_response_contract_checker_accepts_phase_15_after_phase_21(tmp_path: Path):
    payload = {
        "status": "degraded",
        "session_state": {
            "Mode": "DEGRADED",
            "Phase": "1.5-BusinessRules",
            "previous_phase": "2.1-DecisionPack",
            "next_gate_condition": "Proceed to Phase 3A",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Proceed to Phase 3A API inventory",
            "Why": "Phase 1.5 completed after decision pack",
            "Command": "none",
        },
        "snapshot": {"Confidence": "75%", "Risk": "MEDIUM", "Scope": "repo"},
    }
    f = tmp_path / "valid_15_after_21.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode == 0, f"validator should accept phase 1.5 after phase 2.1:\n{r.stdout}\n{r.stderr}"


@pytest.mark.governance
def test_response_contract_checker_rejects_phase_history_where_15_precedes_21(tmp_path: Path):
    payload = {
        "status": "degraded",
        "session_state": {
            "Mode": "DEGRADED",
            "Phase": "1.5-BusinessRules",
            "previous_phase": "4-Implement",
            "phase_history": ["1", "2", "1.5-BusinessRules", "2.1-DecisionPack", "4-Implement", "1.5-BusinessRules"],
            "next_gate_condition": "Proceed to Phase 3A",
        },
        "next_action": {
            "type": "manual_step",
            "Status": "OK",
            "Next": "Proceed to Phase 3A API inventory",
            "Why": "Reopened phase 1.5",
            "Command": "none",
        },
        "snapshot": {"Confidence": "70%", "Risk": "MEDIUM", "Scope": "repo"},
    }
    f = tmp_path / "invalid_phase_history_15_before_21.json"
    f.write_text(json.dumps(payload), encoding="utf-8")

    script = REPO_ROOT / "scripts" / "validate_response_contract.py"
    r = run([sys.executable, str(script), "--input", str(f)])
    assert r.returncode != 0
    assert "phase history invalid: 1.5 cannot occur before 2.1" in (r.stdout + r.stderr)
