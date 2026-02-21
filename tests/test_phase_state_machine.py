from __future__ import annotations

import pytest

from governance.domain.phase_state_machine import (
    PHASE_RANK,
    build_phase_state,
    normalize_phase_token,
    phase_rank,
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


@pytest.mark.governance
def test_phase_rank_map_is_monotonic_for_expected_sequence() -> None:
    sequence = ("1", "1.1", "1.2", "1.3", "1.5", "2", "2.1", "3A", "3B-1", "3B-2", "4", "5", "5.3", "5.4", "5.5", "5.6", "6")
    ranks = [phase_rank(token) for token in sequence]
    assert all(r >= 0 for r in ranks)
    assert ranks == sorted(ranks), f"Phase ranks must be increasing: {list(zip(sequence, ranks))}"


@pytest.mark.governance
def test_phase_rank_unknown_returns_negative_one() -> None:
    assert phase_rank("NOT_A_PHASE") == -1


@pytest.mark.governance
def test_phase_rank_map_covers_all_normalized_tokens() -> None:
    examples = [
        "1", "1.1-Bootstrap", "1.2-RuleLoading", "1.3-AddonScan", "1.5-BusinessRules",
        "2-Discovery", "2.1", "3A-API-Inventory", "3B-1 contract", "3B-2 contract",
        "4-Plan", "5-TestGen", "5.3", "5.4", "5.5", "5.6", "6-PR",
    ]
    for raw in examples:
        token = normalize_phase_token(raw)
        assert token, raw
        assert token in PHASE_RANK, f"Missing PHASE_RANK entry for {token}"
