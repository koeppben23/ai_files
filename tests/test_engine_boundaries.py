from __future__ import annotations

import pytest

from governance.engine.gate_evaluator import evaluate_gate
from governance.engine.invariants import check_single_recovery_action
from governance.engine.state_machine import build_state, transition_to


@pytest.mark.governance
def test_state_machine_returns_same_object_for_no_delta_transition():
    """No-delta transitions should preserve object identity for later diffing."""

    state = build_state(
        phase="4-Implement-Ready",
        active_gate="Scope/Task selection",
        mode="OK",
        next_gate_condition="Concrete implementation target is defined",
    )
    transitioned = transition_to(
        state,
        phase=" 4-Implement-Ready ",
        active_gate=" Scope/Task selection ",
        mode=" OK ",
        next_gate_condition=" Concrete implementation target is defined ",
    )
    assert transitioned is state


@pytest.mark.governance
def test_gate_evaluator_emits_blocked_status_with_reason_code():
    """Blocked evaluations must carry an explicit reason code."""

    evaluation = evaluate_gate(gate_key="P5-Architecture", blocked=True, reason_code="BLOCKED-MISSING-EVIDENCE")
    assert evaluation.gate_key == "P5-Architecture"
    assert evaluation.status == "blocked"
    assert evaluation.reason_code == "BLOCKED-MISSING-EVIDENCE"


@pytest.mark.governance
def test_recovery_invariant_requires_primary_action_and_command():
    """Fail-closed recovery contract requires both fields to be non-empty."""

    assert check_single_recovery_action("Run /start", "/start").valid is True
    assert check_single_recovery_action("", "/start").valid is False
    assert check_single_recovery_action("Run /start", "").valid is False
