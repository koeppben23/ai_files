"""Tests for transition_model module."""

from __future__ import annotations

import pytest

from governance_runtime.application.services.transition_model import (
    resolve_next_action,
    PHASE4_TRANSITIONS,
    PHASE5_TRANSITIONS,
    PHASE6_TRANSITIONS,
    NextActionKind,
    GuardResult,
    _is_phase4,
    _is_phase5,
    _is_phase6,
    _status_error,
    _status_blocked,
)


class TestPhaseHelpers:
    def test_is_phase4_with_phase4(self):
        state = {"phase": "4"}
        assert _is_phase4(state) is True

    def test_is_phase4_false_without_phase(self):
        state = {"active_gate": "Ticket Input Gate"}
        assert _is_phase4(state) is False

    def test_is_phase4_false_for_phase5(self):
        state = {"phase": "5"}
        assert _is_phase4(state) is False

    def test_is_phase5_true(self):
        state = {"phase": "5"}
        assert _is_phase5(state) is True

    def test_is_phase5_subphase(self):
        state = {"phase": "5.4"}
        assert _is_phase5(state) is True

    def test_is_phase5_false(self):
        state = {"phase": "4"}
        assert _is_phase5(state) is False

    def test_is_phase6_true(self):
        state = {"phase": "6"}
        assert _is_phase6(state) is True

    def test_is_phase6_false(self):
        state = {"phase": "5"}
        assert _is_phase6(state) is False


class TestStatusHelpers:
    def test_status_error_true(self):
        state = {"status": "error"}
        assert _status_error(state) is True

    def test_status_error_false(self):
        state = {"status": "OK"}
        assert _status_error(state) is False

    def test_status_blocked_true(self):
        state = {"status": "blocked"}
        assert _status_blocked(state) is True

    def test_status_blocked_false(self):
        state = {"status": "OK"}
        assert _status_blocked(state) is False


class TestResolveNextAction:
    def test_error_status_returns_continue(self):
        state = {"status": "error", "phase": "4"}
        result = resolve_next_action(state)
        assert result.command == "/continue"
        assert result.kind == NextActionKind.RECOVERY
        assert result.reason == "error-status"

    def test_blocked_status_returns_continue(self):
        state = {"status": "blocked", "phase": "4"}
        result = resolve_next_action(state)
        assert result.command == "/continue"
        assert result.kind == NextActionKind.BLOCKED
        assert result.reason == "blocked-status"

    def test_phase4_ticket_input_gate(self):
        state = {"phase": "4", "active_gate": "Ticket Input Gate"}
        result = resolve_next_action(state)
        assert result.command == "/ticket"
        assert result.kind == NextActionKind.NORMAL

    def test_phase4_plan_record_preparation_gate(self):
        state = {
            "phase": "4",
            "active_gate": "Plan Record Preparation Gate",
            "plan_record_versions": 0,
        }
        result = resolve_next_action(state)
        assert result.command == "/continue"
        assert result.kind == NextActionKind.NORMAL

    def test_phase5_returns_continue(self):
        state = {"phase": "5", "active_gate": "Test Quality Gate"}
        result = resolve_next_action(state)
        assert result.command == "/continue"
        assert result.kind == NextActionKind.NORMAL

    def test_phase6_workflow_complete(self):
        state = {"phase": "6", "active_gate": "Workflow Complete"}
        result = resolve_next_action(state)
        assert result.command == "/implement"
        assert result.kind == NextActionKind.TERMINAL

    def test_phase6_implementation_presentation_gate(self):
        state = {"phase": "6", "active_gate": "Implementation Presentation Gate"}
        result = resolve_next_action(state)
        assert result.command == "/implementation-decision"
        assert result.kind == NextActionKind.NORMAL

    def test_phase6_evidence_presentation_gate(self):
        state = {"phase": "6", "active_gate": "Evidence Presentation Gate"}
        result = resolve_next_action(state)
        assert result.command == "/review-decision"
        assert result.kind == NextActionKind.NORMAL

    def test_phase6_implementation_execution(self):
        state = {"phase": "6", "active_gate": "Implementation Execution In Progress"}
        result = resolve_next_action(state)
        assert result.command == "/continue"
        assert result.kind == NextActionKind.NORMAL

    def test_default_returns_continue(self):
        state = {"phase": "unknown"}
        result = resolve_next_action(state)
        assert result.command == "/continue"
        assert result.kind == NextActionKind.NORMAL
        assert result.reason == "default-progress"


class TestTransitionTables:
    def test_phase4_transitions_exist(self):
        assert len(PHASE4_TRANSITIONS.transitions) > 0

    def test_phase5_transitions_exist(self):
        assert len(PHASE5_TRANSITIONS.transitions) > 0

    def test_phase6_transitions_exist(self):
        assert len(PHASE6_TRANSITIONS.transitions) > 0

    def test_find_matching_returns_transition(self):
        t = PHASE4_TRANSITIONS.find_matching(
            {"phase": "4"},
            "ticket input gate"
        )
        assert t is not None
        assert t.command == "/ticket"

    def test_find_matching_returns_none_for_unknown_gate(self):
        t = PHASE4_TRANSITIONS.find_matching(
            {"phase": "4"},
            "unknown gate"
        )
        assert t is None
