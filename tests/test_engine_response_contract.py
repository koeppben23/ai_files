from __future__ import annotations

from typing import Any, cast

import pytest

from governance.engine.response_contract import NextAction, Snapshot, build_compat_response, build_strict_response


@pytest.mark.governance
def test_build_strict_response_produces_deterministic_envelope():
    """Strict responses should include canonical fields and normalized status."""

    payload = build_strict_response(
        status="ok",
        session_state={"phase": "1.1-Bootstrap"},
        next_action=NextAction(type="manual_step", command="Provide task scope"),
        snapshot=Snapshot(confidence="High", risk="Low", scope="Bootstrap"),
        reason_payload={"status": "OK", "reason_code": "none"},
    )
    payload = cast(dict[str, Any], payload)
    assert payload["mode"] == "STRICT"
    assert payload["status"] == "OK"
    assert payload["next_action"]["type"] == "manual_step"
    assert payload["snapshot"]["confidence"] == "High"


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
    assert payload["next_action"]["type"] == "reply_with_one_number"
    assert payload["required_inputs"] == ("Provide evidence",)
