"""Tests for state invariants - executable rules that constrain valid state forms."""

import pytest

from governance_runtime.application.services.state_invariants import (
    check_all_invariants,
    check_invariant_phase6_completed_requires_review_package,
    check_invariant_evidence_gate_only_in_phase6,
    check_invariant_implementation_review_only_in_phase6,
    check_invariant_phase5_completed_not_stale,
    check_invariant_review_package_when_presented,
    check_invariant_phase6_loop_status_consistent,
    check_invariant_rework_gate_requires_changes_requested,
)


class TestPhase6CompletedRequiresReviewPackage:
    def test_valid_when_review_package_presented(self):
        state = {"phase6_state": "6.complete", "review_package": {"presented": True}}
        valid, _ = check_invariant_phase6_completed_requires_review_package(state)
        assert valid is True

    def test_invalid_when_not_presented(self):
        state = {"phase6_state": "6.complete", "review_package": {"presented": False}}
        valid, msg = check_invariant_phase6_completed_requires_review_package(state)
        assert valid is False
        assert "INV-001" in msg

    def test_valid_when_not_phase6_completed(self):
        state = {"phase6_state": "6.execution"}
        valid, _ = check_invariant_phase6_completed_requires_review_package(state)
        assert valid is True


class TestEvidenceGateOnlyInPhase6:
    def test_valid_when_phase6(self):
        state = {"active_gate": "Evidence Presentation Gate", "phase": "6-PostFlight"}
        valid, _ = check_invariant_evidence_gate_only_in_phase6(state)
        assert valid is True

    def test_invalid_when_phase5(self):
        state = {"active_gate": "Evidence Presentation Gate", "phase": "5-ArchitectureReview"}
        valid, msg = check_invariant_evidence_gate_only_in_phase6(state)
        assert valid is False
        assert "INV-100" in msg

    def test_valid_when_different_gate(self):
        state = {"active_gate": "Ticket Input Gate", "phase": "4"}
        valid, _ = check_invariant_evidence_gate_only_in_phase6(state)
        assert valid is True


class TestImplementationReviewOnlyInPhase6:
    def test_valid_when_phase6(self):
        state = {"implementation_review": {"iteration": 1}, "phase": "6-PostFlight"}
        valid, _ = check_invariant_implementation_review_only_in_phase6(state)
        assert valid is True

    def test_invalid_when_phase5(self):
        state = {"implementation_review": {"iteration": 1}, "phase": "5-ArchitectureReview"}
        valid, msg = check_invariant_implementation_review_only_in_phase6(state)
        assert valid is False
        assert "INV-300" in msg


class TestPhase5CompletedNotStale:
    def test_valid_when_phase6(self):
        state = {"phase5_completed": True, "phase": "6-PostFlight"}
        valid, _ = check_invariant_phase5_completed_not_stale(state)
        assert valid is True

    def test_valid_when_phase5(self):
        state = {"phase5_completed": True, "phase": "5-ArchitectureReview"}
        valid, _ = check_invariant_phase5_completed_not_stale(state)
        assert valid is True

    def test_invalid_when_phase4(self):
        state = {"phase5_completed": True, "phase": "4"}
        valid, msg = check_invariant_phase5_completed_not_stale(state)
        assert valid is False
        assert "INV-002" in msg


class TestReviewPackageWhenPresented:
    def test_valid_when_has_review_object(self):
        state = {"review_package": {"presented": True, "review_object": "Test"}}
        valid, _ = check_invariant_review_package_when_presented(state)
        assert valid is True

    def test_invalid_when_no_review_object(self):
        state = {"review_package": {"presented": True}}
        valid, msg = check_invariant_review_package_when_presented(state)
        assert valid is False
        assert "INV-200" in msg

    def test_valid_when_not_presented(self):
        state = {"review_package": {"presented": False}}
        valid, _ = check_invariant_review_package_when_presented(state)
        assert valid is True


class TestPhase6LoopStatusConsistent:
    def test_valid_when_not_in_progress(self):
        state = {"phase6_state": "6.complete", "implementation_review_complete": True}
        valid, _ = check_invariant_phase6_loop_status_consistent(state)
        assert valid is True

    def test_valid_when_in_progress_and_not_complete(self):
        state = {"phase6_state": "6.execution", "implementation_review": {"implementation_review_complete": False}}
        valid, _ = check_invariant_phase6_loop_status_consistent(state)
        assert valid is True

    def test_invalid_when_in_progress_and_complete(self):
        state = {"phase6_state": "6.execution", "implementation_review": {"implementation_review_complete": True}}
        valid, msg = check_invariant_phase6_loop_status_consistent(state)
        assert valid is False
        assert "INV-010" in msg


class TestReworkGateRequiresChangesRequested:
    def test_valid_when_phase6(self):
        state = {"active_gate": "Rework Clarification Gate", "phase": "6-PostFlight"}
        valid, _ = check_invariant_rework_gate_requires_changes_requested(state)
        assert valid is True

    def test_invalid_when_phase5(self):
        state = {"active_gate": "Rework Clarification Gate", "phase": "5-ArchitectureReview"}
        valid, msg = check_invariant_rework_gate_requires_changes_requested(state)
        assert valid is False
        assert "INV-110" in msg


class TestCheckAllInvariants:
    def test_empty_state_passes(self):
        violations = check_all_invariants({})
        assert violations == []

    def test_multiple_violations_detected(self):
        state = {
            "phase6_state": "6.complete",
            "review_package": {"presented": False},
            "active_gate": "Evidence Presentation Gate",
            "phase": "5-ArchitectureReview",
        }
        violations = check_all_invariants(state)
        assert len(violations) >= 2
        assert any("INV-001" in v for v in violations)
        assert any("INV-100" in v for v in violations)

    def test_valid_phase6_state(self):
        state = {
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "phase6_state": "6.complete",
            "review_package": {"presented": True, "review_object": "Test"},
            "implementation_review": {"implementation_review_complete": True, "iteration": 3},
            "phase5_completed": True,
        }
        violations = check_all_invariants(state)
        assert violations == []
