from __future__ import annotations

import json
from typing import Any, cast

import pytest

from governance.engine.response_contract import (
    SESSION_SNAPSHOT_MAX_CHARS,
    SESSION_SNAPSHOT_WHITELIST,
    NextAction,
    Snapshot,
    build_compat_response,
    build_strict_response,
)


@pytest.mark.governance
def test_build_strict_response_produces_deterministic_envelope():
    """Strict responses should include canonical fields and normalized status."""

    payload = build_strict_response(
        status="ok",
        session_state={
            "phase": "1.1-Bootstrap",
            "effective_operating_mode": "user",
            "activation_hash": "ab" * 32,
            "ruleset_hash": "cd" * 32,
            "repo_fingerprint": "repo-123",
            "super_verbose_field": "must-not-appear-by-default",
        },
        next_action=NextAction(type="manual_step", command="Continue bootstrap discovery"),
        snapshot=Snapshot(confidence="High", risk="Low", scope="Bootstrap"),
        reason_payload={"status": "OK", "reason_code": "none"},
    )
    payload = cast(dict[str, Any], payload)
    assert payload["mode"] == "STRICT"
    assert payload["status"] == "OK"
    assert payload["decision_outcome"] == "ALLOW"
    assert payload["next_action"]["type"] == "manual_step"
    assert payload["snapshot"]["confidence"] == "High"
    assert set(payload["session_state"].keys()) == set(SESSION_SNAPSHOT_WHITELIST)
    assert payload["session_state"]["activation_hash"] == "ab" * 32
    assert payload["session_state"]["active_gate.status"] == "OK"
    assert payload["session_state"]["active_gate.decision_outcome"] == "ALLOW"
    assert "session_state_full" not in payload
    compact_len = len(json.dumps(payload["session_state"], ensure_ascii=True, separators=(",", ":")))
    assert compact_len <= SESSION_SNAPSHOT_MAX_CHARS


@pytest.mark.governance
def test_build_strict_response_preserves_reason_code_casing_in_snapshot():
    """Snapshot reason code must match reason payload casing exactly."""

    payload = build_strict_response(
        status="BLOCKED",
        session_state={
            "phase": "1.1-Bootstrap",
            "effective_operating_mode": "user",
            "activation_hash": "ab" * 32,
            "ruleset_hash": "cd" * 32,
            "repo_fingerprint": "repo-123",
        },
        next_action=NextAction(type="command", command="/start"),
        snapshot=Snapshot(confidence="High", risk="Low", scope="Bootstrap"),
        reason_payload={"status": "BLOCKED", "reason_code": "BLOCKED-EXEC-DISALLOWED"},
    )
    payload = cast(dict[str, Any], payload)
    assert payload["session_state"]["active_gate.reason_code"] == "BLOCKED-EXEC-DISALLOWED"
    assert payload["decision_outcome"] == "BLOCKED"


@pytest.mark.governance
def test_build_strict_response_emits_full_state_only_for_explicit_intent():
    """Full session dump should only be present for explicit diagnostics intent."""

    full_state = {
        "phase": "1.1-Bootstrap",
        "effective_operating_mode": "user",
        "activation_hash": "11" * 32,
        "ruleset_hash": "22" * 32,
        "repo_fingerprint": "repo-xyz",
        "large_payload": {"x": "y"},
    }
    payload = build_strict_response(
        status="WARN",
        session_state=full_state,
        next_action=NextAction(type="manual_step", command="Review warning"),
        snapshot=Snapshot(confidence="Medium", risk="Medium", scope="Bootstrap"),
        reason_payload={"status": "WARN", "reason_code": "WARN-PERMISSION-LIMITED"},
        detail_intent="show_diagnostics",
    )
    payload = cast(dict[str, Any], payload)
    assert payload["session_state"]["repo_fingerprint"] == "repo-xyz"
    assert payload["session_state_full"] == full_state


@pytest.mark.governance
def test_build_strict_response_requires_activation_hash_in_snapshot():
    """Default snapshot projection should fail closed without activation hash."""

    with pytest.raises(ValueError, match="activation_hash"):
        build_strict_response(
            status="OK",
            session_state={"phase": "1.1-Bootstrap"},
            next_action=NextAction(type="manual_step", command="Proceed"),
            snapshot=Snapshot(confidence="High", risk="Low", scope="Bootstrap"),
            reason_payload={"status": "OK", "reason_code": "none"},
        )


@pytest.mark.governance
def test_build_compat_response_requires_inputs_when_blocked():
    """Blocked compat responses must carry required input guidance."""

    with pytest.raises(ValueError, match="required_inputs"):
        build_compat_response(
            status="BLOCKED",
            required_inputs=(),
            recovery="Run one recovery command",
            next_action=NextAction(type="command", command="/start"),
            reason_payload={"status": "BLOCKED", "reason_code": "BLOCKED-X"},
        )


@pytest.mark.governance
def test_build_compat_response_accepts_single_next_action_mechanism():
    """Compat responses should preserve a single explicit next action."""

    payload = build_compat_response(
        status="NOT_VERIFIED",
        required_inputs=("Provide evidence",),
        recovery="Collect host evidence and rerun.",
        next_action=NextAction(type="reply_with_one_number", command="1"),
        reason_payload={"status": "NOT_VERIFIED", "reason_code": "NOT_VERIFIED-MISSING-EVIDENCE"},
    )
    payload = cast(dict[str, Any], payload)
    assert payload["mode"] == "COMPAT"
    assert payload["status"] == "NOT_VERIFIED"
    assert payload["decision_outcome"] == "ALLOW"
    assert payload["next_action"]["type"] == "reply_with_one_number"
    assert payload["required_inputs"] == ("Provide evidence",)


@pytest.mark.governance
def test_build_strict_response_rejects_phase_2_ticket_prompt_command():
    with pytest.raises(ValueError, match="phase alignment"):
        build_strict_response(
            status="OK",
            session_state={
                "phase": "2-RepoDiscovery",
                "activation_hash": "ab" * 32,
                "ruleset_hash": "cd" * 32,
            },
            next_action=NextAction(type="manual_step", command="Provide task/ticket to plan"),
            snapshot=Snapshot(confidence="High", risk="Low", scope="Bootstrap"),
            reason_payload={"status": "OK", "reason_code": "none"},
        )


@pytest.mark.governance
def test_build_strict_response_accepts_phase_2_scope_command():
    payload = build_strict_response(
        status="OK",
        session_state={
            "phase": "2-RepoDiscovery",
            "workspace_ready": True,
            "activation_hash": "ab" * 32,
            "ruleset_hash": "cd" * 32,
        },
        next_action=NextAction(type="manual_step", command="Set working set and component scope"),
        snapshot=Snapshot(confidence="High", risk="Low", scope="Bootstrap"),
        reason_payload={"status": "OK", "reason_code": "none"},
    )
    payload = cast(dict[str, Any], payload)
    assert payload["status"] == "OK"
    assert payload["decision_outcome"] == "ALLOW"
