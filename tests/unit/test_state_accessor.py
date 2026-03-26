"""Tests for state_accessor module."""

from __future__ import annotations

import pytest

from governance_runtime.application.services.state_accessor import (
    get_phase,
    get_active_gate,
    get_status,
    get_next_gate_condition,
    get_mode,
    get_review_iterations,
    get_max_review_iterations,
    get_min_review_iterations,
    get_revision_delta,
    is_review_complete,
    is_workflow_complete,
    is_implementation_authorized,
    is_implementation_blocked,
    get_plan_versions,
    get_rework_clarification_input,
    is_phase5_completed,
)


class TestGetPhase:
    def test_canonical_phase(self):
        state = {"phase": "5-ArchitectureReview"}
        assert get_phase(state) == "5-ArchitectureReview"

    def test_legacy_phase(self):
        state = {"phase": "6-PostFlight"}
        assert get_phase(state) == "6-PostFlight"

    def test_canonical_takes_precedence(self):
        state = {"phase": "legacy", "phase": "canonical"}
        assert get_phase(state) == "canonical"

    def test_empty_state(self):
        state = {}
        assert get_phase(state) == ""


class TestGetActiveGate:
    def test_active_gate(self):
        state = {"active_gate": "Evidence Presentation Gate"}
        assert get_active_gate(state) == "Evidence Presentation Gate"

    def test_empty_state(self):
        state = {}
        assert get_active_gate(state) == ""


class TestGetStatus:
    def test_status(self):
        state = {"status": "OK"}
        assert get_status(state) == "OK"

    def test_empty_state(self):
        state = {}
        assert get_status(state) == ""


class TestGetNextGateCondition:
    def test_condition(self):
        state = {"next_gate_condition": "Run /continue to proceed"}
        assert get_next_gate_condition(state) == "Run /continue to proceed"

    def test_empty_state(self):
        state = {}
        assert get_next_gate_condition(state) == ""


class TestGetMode:
    def test_mode(self):
        state = {"mode": "IN_PROGRESS"}
        assert get_mode(state) == "IN_PROGRESS"

    def test_empty_state(self):
        state = {}
        assert get_mode(state) == ""


class TestReviewIterations:
    def test_get_review_iterations(self):
        state = {"phase6_review_iterations": 5}
        assert get_review_iterations(state) == 5

    def test_get_review_iterations_default(self):
        state = {}
        assert get_review_iterations(state) == 0

    def test_get_max_review_iterations(self):
        state = {"phase6_max_review_iterations": 10}
        assert get_max_review_iterations(state) == 10

    def test_get_min_review_iterations(self):
        state = {"phase6_min_review_iterations": 2}
        assert get_min_review_iterations(state) == 2

    def test_get_revision_delta(self):
        state = {"phase6_revision_delta": "changed"}
        assert get_revision_delta(state) == "changed"


class TestBooleans:
    def test_is_review_complete_true(self):
        state = {"implementation_review_complete": True}
        assert is_review_complete(state) is True

    def test_is_review_complete_false(self):
        state = {"implementation_review_complete": False}
        assert is_review_complete(state) is False

    def test_is_review_complete_from_review_block(self):
        state = {"ImplementationReview": {"implementation_review_complete": True}}
        assert is_review_complete(state) is True

    def test_is_workflow_complete_true(self):
        state = {"workflow_complete": True}
        assert is_workflow_complete(state) is True

    def test_is_workflow_complete_false(self):
        state = {"workflow_complete": False}
        assert is_workflow_complete(state) is False

    def test_is_implementation_authorized_true(self):
        state = {"implementation_authorized": True}
        assert is_implementation_authorized(state) is True

    def test_is_implementation_blocked_true(self):
        state = {"implementation_blocked": True}
        assert is_implementation_blocked(state) is True


class TestPlanVersions:
    def test_get_plan_versions(self):
        state = {"plan_record_versions": 3}
        assert get_plan_versions(state) == 3

    def test_get_plan_versions_default(self):
        state = {}
        assert get_plan_versions(state) == 0


class TestReworkClarification:
    def test_get_rework_clarification_input(self):
        state = {"rework_clarification_input": "Please fix the issue"}
        assert get_rework_clarification_input(state) == "Please fix the issue"


class TestPhase5:
    def test_is_phase5_completed_true(self):
        state = {"phase5_completed": True}
        assert is_phase5_completed(state) is True

    def test_is_phase5_completed_false(self):
        state = {"phase5_completed": False}
        assert is_phase5_completed(state) is False

    def test_is_phase5_completed_default(self):
        state = {}
        assert is_phase5_completed(state) is False
