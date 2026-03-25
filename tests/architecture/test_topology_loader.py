"""Tests for TopologyLoader - WP2: Topology Operative Authority.

Tests cover:
- Happy Path: State machine transitions work correctly
- Negative: Invalid states/events raise errors
- Edge Cases: Terminal states, parent states, reachability
- Regression: Real topology.yaml loads correctly
"""

from __future__ import annotations

import pytest

from governance_runtime.kernel.topology_loader import (
    TopologyLoader,
    StateDef,
    TransitionDef,
    StateNotFoundError,
    InvalidTransitionError,
    resolve_transition,
    validate_state_exists,
    is_state_reachable,
)


@pytest.fixture(autouse=True)
def reset_loader():
    """Reset loader before each test."""
    TopologyLoader.reset()
    yield
    TopologyLoader.reset()


class TestTopologyLoaderBasic:
    """Happy Path: Basic topology queries."""

    def test_get_start_state(self):
        """Happy: Get start state from topology."""
        start = TopologyLoader.get_start_state_id()
        assert start == "0"

    def test_get_state_returns_state_def(self):
        """Happy: get_state returns StateDef for existing state."""
        state = TopologyLoader.get_state("6.approved")
        
        assert isinstance(state, StateDef)
        assert state.id == "6.approved"
        assert state.terminal is False
        assert state.parent == "6"

    def test_get_state_not_found_raises_error(self):
        """Negative: Unknown state raises StateNotFoundError."""
        with pytest.raises(StateNotFoundError) as exc_info:
            TopologyLoader.get_state("nonexistent")
        
        assert "not found" in str(exc_info.value).lower()

    def test_is_state_terminal(self):
        """Happy: Terminal state check."""
        assert TopologyLoader.is_state_terminal("6.complete") is True
        assert TopologyLoader.is_state_terminal("6.approved") is False
        assert TopologyLoader.is_state_terminal("0") is False


class TestTopologyLoaderTransitions:
    """Transition resolution tests."""

    def test_get_next_state_happy(self):
        """Happy: Get next state for valid transition."""
        # 6.execution + implementation_accepted -> 6.internal_review
        next_state = TopologyLoader.get_next_state("6.execution", "implementation_accepted")
        assert next_state == "6.internal_review"

    def test_get_next_state_multiple_events(self):
        """Happy: Different events from same state."""
        # 6.presentation has multiple transitions
        approved = TopologyLoader.get_next_state("6.presentation", "workflow_approved")
        rework = TopologyLoader.get_next_state("6.presentation", "review_changes_requested")
        rejected = TopologyLoader.get_next_state("6.presentation", "review_rejected")
        
        assert approved == "6.approved"
        assert rework == "6.rework"
        assert rejected == "6.rejected"

    def test_get_next_state_invalid_event_raises_error(self):
        """Negative: Invalid event raises InvalidTransitionError."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            TopologyLoader.get_next_state("6.execution", "invalid_event")
        
        assert "invalid_event" in str(exc_info.value)

    def test_get_next_state_invalid_state_raises_error(self):
        """Negative: Invalid state raises StateNotFoundError."""
        with pytest.raises(StateNotFoundError):
            TopologyLoader.get_next_state("nonexistent", "default")

    def test_has_event(self):
        """Happy: Check if event exists for state."""
        assert TopologyLoader.has_event("6.execution", "implementation_accepted") is True
        assert TopologyLoader.has_event("6.execution", "workflow_complete") is True
        assert TopologyLoader.has_event("6.execution", "invalid_event") is False

    def test_get_state_transitions(self):
        """Happy: Get all transitions for a state."""
        transitions = TopologyLoader.get_state_transitions("6.presentation")
        
        assert len(transitions) >= 5
        assert any(t.event == "workflow_approved" for t in transitions)
        assert any(t.event == "review_changes_requested" for t in transitions)


class TestTopologyLoaderPhase6:
    """Phase 6 specific transition tests."""

    def test_6_approved_to_6_execution(self):
        """Happy: /implement triggers implementation_started -> 6.execution."""
        next_state = TopologyLoader.get_next_state("6.approved", "implementation_started")
        assert next_state == "6.execution"

    def test_6_execution_to_6_blocked(self):
        """Happy: implementation_blocked -> 6.blocked."""
        next_state = TopologyLoader.get_next_state("6.execution", "implementation_blocked")
        assert next_state == "6.blocked"

    def test_6_blocked_to_6_execution(self):
        """Happy: implementation_started from 6.blocked -> 6.execution."""
        next_state = TopologyLoader.get_next_state("6.blocked", "implementation_started")
        assert next_state == "6.execution"

    def test_6_execution_to_6_complete(self):
        """Happy: workflow_complete -> 6.complete."""
        next_state = TopologyLoader.get_next_state("6.execution", "workflow_complete")
        assert next_state == "6.complete"

    def test_6_rejected_to_4(self):
        """Happy: 6.rejected -> 4 (return to replanning)."""
        next_state = TopologyLoader.get_next_state("6.rejected", "default")
        assert next_state == "4"

    def test_6_complete_is_terminal(self):
        """Happy: 6.complete is terminal with no transitions."""
        assert TopologyLoader.is_state_terminal("6.complete") is True
        transitions = TopologyLoader.get_state_transitions("6.complete")
        assert len(transitions) == 0


class TestTopologyLoaderParentStates:
    """Parent/substate relationship tests."""

    def test_phase6_substates_have_parent(self):
        """Happy: Phase 6 substates have parent='6'."""
        substates = ["6.internal_review", "6.presentation", "6.execution", 
                     "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"]
        
        for substate in substates:
            state = TopologyLoader.get_state(substate)
            assert state.parent == "6", f"{substate} should have parent='6'"

    def test_parent_state_exists(self):
        """Happy: Parent state 6 exists."""
        parent = TopologyLoader.get_state("6")
        assert parent.id == "6"
        assert parent.terminal is False

    def test_get_parent_state(self):
        """Happy: Get parent of a substate."""
        parent_id = TopologyLoader.get_parent_state("6.approved")
        assert parent_id == "6"

    def test_get_parent_state_none(self):
        """Happy: State without parent returns None."""
        parent_id = TopologyLoader.get_parent_state("4")
        assert parent_id is None

    def test_is_substate(self):
        """Happy: Check substate relationship."""
        assert TopologyLoader.is_substate("6.approved", "6") is True
        assert TopologyLoader.is_substate("6.execution", "6") is True
        assert TopologyLoader.is_substate("4", "6") is False


class TestTopologyLoaderQueries:
    """Query tests for topology."""

    def test_get_all_states(self):
        """Happy: Get all state IDs."""
        states = TopologyLoader.get_all_states()
        
        assert "0" in states
        assert "6.approved" in states
        assert "6.complete" in states
        assert len(states) > 20  # Topology has many states

    def test_get_all_events(self):
        """Happy: Get all unique events."""
        events = TopologyLoader.get_all_events()
        
        assert "implementation_started" in events
        assert "workflow_approved" in events
        assert "workflow_complete" in events
        assert "default" not in events  # default is special, not a real event

    def test_get_event_target_map(self):
        """Happy: Get event-to-target mapping."""
        mapping = TopologyLoader.get_event_target_map("6.presentation")
        
        assert mapping["workflow_approved"] == "6.approved"
        assert mapping["review_changes_requested"] == "6.rework"
        assert mapping["review_rejected"] == "6.rejected"


class TestTopologyLoaderPublicAPI:
    """Tests for public API functions."""

    def test_resolve_transition(self):
        """Happy: resolve_transition works like get_next_state."""
        next_state = resolve_transition("6.execution", "implementation_accepted")
        assert next_state == "6.internal_review"

    def test_validate_state_exists(self):
        """Happy: validate_state_exists returns StateDef."""
        state = validate_state_exists("6.approved")
        assert state.id == "6.approved"

    def test_validate_state_exists_raises(self):
        """Negative: validate_state_exists raises for invalid state."""
        with pytest.raises(StateNotFoundError):
            validate_state_exists("nonexistent")


class TestTopologyLoaderReachability:
    """Reachability tests."""

    def test_start_state_is_reachable(self):
        """Happy: Start state is always reachable."""
        assert is_state_reachable("0") is True

    def test_phase6_states_are_reachable(self):
        """Happy: Phase 6 states are reachable from start."""
        assert is_state_reachable("6.approved") is True
        assert is_state_reachable("6.execution") is True
        assert is_state_reachable("6.complete") is True

    def test_all_topology_states_are_reachable(self):
        """Regression: All states in topology are reachable."""
        states = TopologyLoader.get_all_states()
        
        for state_id in states:
            assert is_state_reachable(state_id), f"State '{state_id}' is not reachable"


class TestTopologyLoaderRegression:
    """Regression: Real topology.yaml loads correctly."""

    def test_loads_real_topology(self):
        """Regression: Real topology.yaml loads successfully."""
        state = TopologyLoader.get_state("6.internal_review")
        
        assert state.parent == "6"
        assert state.terminal is False

    def test_real_topology_has_correct_structure(self):
        """Regression: Real topology has expected states."""
        # Phase 6 states
        assert TopologyLoader.get_state("6.approved").id == "6.approved"
        assert TopologyLoader.get_state("6.execution").id == "6.execution"
        assert TopologyLoader.get_state("6.complete").id == "6.complete"
        
        # Only 6.complete is terminal in phase 6
        assert TopologyLoader.is_state_terminal("6.complete") is True
        assert TopologyLoader.is_state_terminal("6.approved") is False
        assert TopologyLoader.is_state_terminal("6.execution") is False

    def test_real_topology_transitions_consistent(self):
        """Regression: Transition targets exist in topology."""
        states = TopologyLoader.get_all_states()
        state_set = set(states)
        
        for state_id in states:
            for transition in TopologyLoader.get_state_transitions(state_id):
                assert transition.target in state_set, \
                    f"Transition {transition.id} from {state_id} targets non-existent state {transition.target}"

    def test_start_state_is_0(self):
        """Regression: Start state is '0'."""
        assert TopologyLoader.get_start_state_id() == "0"
