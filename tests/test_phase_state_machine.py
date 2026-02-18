from __future__ import annotations

import pytest

from governance.domain.phase_state_machine import (
    build_phase_state,
    normalize_phase_token,
    resolve_phase_policy,
    transition_phase_state,
)


@pytest.mark.governance
@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("3b-2 contract validation", "3B-2"),
        (" 5.4-implementation ", "5.4"),
        ("2.1", "2.1"),
        ("not-a-phase", ""),
        (None, ""),
    ),
)
def test_normalize_phase_token(raw: object, expected: str):
    assert normalize_phase_token(raw) == expected


@pytest.mark.governance
@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("3A", False),
        ("4", True),
        ("5.6", True),
        ("unknown", False),
    ),
)
def test_resolve_phase_policy_ticket_prompt_gate(raw: object, expected: bool):
    assert resolve_phase_policy(raw).ticket_required_allowed is expected


@pytest.mark.governance
def test_transition_phase_state_returns_same_object_for_no_delta() -> None:
    state = build_phase_state(
        phase="4-Implement-Ready",
        active_gate="Scope/Task selection",
        mode="OK",
        next_gate_condition="Concrete implementation target is defined",
    )
    transitioned = transition_phase_state(
        state,
        phase=" 4-Implement-Ready ",
        active_gate=" Scope/Task selection ",
        mode=" OK ",
        next_gate_condition=" Concrete implementation target is defined ",
    )
    assert transitioned is state
