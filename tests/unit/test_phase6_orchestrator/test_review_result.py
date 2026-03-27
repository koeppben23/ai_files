"""Tests for ReviewResult subsystem."""

from __future__ import annotations

import pytest

from governance_runtime.application.services.phase6_review_orchestrator.review_result import (
    ReviewResult,
    ReviewIteration,
    ReviewLoopResult,
    ReviewOutcome,
    CompletionStatus,
)


class TestReviewIteration:
    """Tests for ReviewIteration dataclass."""

    def test_is_complete_true_when_completed(self):
        """is_complete returns True when outcome is COMPLETED."""
        iteration = ReviewIteration(
            iteration=1,
            input_digest="abc",
            output_digest="def",
            revision_delta="changed",
            outcome=ReviewOutcome.COMPLETED,
            llm_invoked=True,
            llm_valid=True,
            llm_verdict="approve",
        )
        assert iteration.is_complete is True

    def test_is_complete_false_when_revised(self):
        """is_complete returns False when outcome is REVISED."""
        iteration = ReviewIteration(
            iteration=1,
            input_digest="abc",
            output_digest="def",
            revision_delta="changed",
            outcome=ReviewOutcome.REVISED,
            llm_invoked=True,
            llm_valid=False,
            llm_verdict="changes_requested",
        )
        assert iteration.is_complete is False


class TestReviewLoopResult:
    """Tests for ReviewLoopResult dataclass."""

    @pytest.fixture
    def complete_result(self):
        """A completed review loop result."""
        return ReviewLoopResult(
            iterations=(
                ReviewIteration(
                    iteration=1,
                    input_digest="a",
                    output_digest="b",
                    revision_delta="changed",
                    outcome=ReviewOutcome.REVISED,
                    llm_invoked=True,
                    llm_valid=False,
                    llm_verdict="changes_requested",
                    llm_pipeline_mode=True,
                    llm_binding_role="review",
                    llm_binding_source="env:AI_GOVERNANCE_REVIEW_BINDING",
                ),
                ReviewIteration(
                    iteration=2,
                    input_digest="b",
                    output_digest="c",
                    revision_delta="changed",
                    outcome=ReviewOutcome.COMPLETED,
                    llm_invoked=True,
                    llm_valid=True,
                    llm_verdict="approve",
                    llm_pipeline_mode=True,
                    llm_binding_role="review",
                    llm_binding_source="env:AI_GOVERNANCE_REVIEW_BINDING",
                ),
            ),
            final_iteration=2,
            max_iterations=3,
            min_iterations=1,
            prev_digest="a",
            curr_digest="c",
            revision_delta="changed",
            completion_status=CompletionStatus.PHASE6_COMPLETED,
            implementation_review_complete=True,
        )

    @pytest.fixture
    def blocked_result(self):
        """A blocked review loop result."""
        return ReviewLoopResult(
            iterations=(),
            final_iteration=0,
            max_iterations=3,
            min_iterations=1,
            prev_digest="",
            curr_digest="",
            revision_delta="changed",
            completion_status=CompletionStatus.PHASE6_IN_PROGRESS,
            implementation_review_complete=False,
            blocked=True,
            block_reason="effective-review-policy-unavailable",
            block_reason_code="BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE",
            recovery_action="Load rulebooks",
        )

    def test_is_complete_true(self, complete_result):
        """is_complete returns True when status is PHASE6_COMPLETED."""
        assert complete_result.is_complete is True

    def test_is_complete_false_when_blocked(self, blocked_result):
        """is_complete returns False when blocked."""
        assert blocked_result.is_complete is False

    def test_to_state_updates_for_complete(self, complete_result):
        """to_state_updates returns proper state dict for completed review."""
        updates = complete_result.to_state_updates()
        assert updates["implementation_review_complete"] is True
        assert updates["phase6_review_iterations"] == 2
        assert updates["phase6_state"] == "6.complete"
        assert updates["phase6_review_pipeline_mode"] is True
        assert updates["phase6_review_binding_role"] == "review"
        assert updates["phase6_review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"
        assert "ImplementationReview" in updates
        assert updates["ImplementationReview"]["iteration"] == 2
        assert updates["ImplementationReview"]["llm_review_binding_role"] == "review"
        assert updates["ImplementationReview"]["llm_review_pipeline_mode"] is True
        assert (
            updates["ImplementationReview"]["llm_review_binding_source"]
            == "env:AI_GOVERNANCE_REVIEW_BINDING"
        )

    def test_to_state_updates_for_blocked(self, blocked_result):
        """to_state_updates returns blocker info for blocked review."""
        updates = blocked_result.to_state_updates()
        assert updates["phase6_blocker_code"] == "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"
        assert updates["phase6_blocker_reason"] == "effective-review-policy-unavailable"
        assert updates["phase6_review_pipeline_mode"] is None
        assert updates["phase6_review_binding_role"] == "review"
        assert updates["phase6_review_binding_source"] == ""

    def test_to_audit_events(self, complete_result):
        """to_audit_events returns list of audit event dicts."""
        events = complete_result.to_audit_events()
        assert len(events) == 2
        assert events[0]["event"] == "phase6-implementation-review-iteration"
        assert events[0]["iteration"] == 1
        assert events[1]["iteration"] == 2
        assert events[1]["outcome"] == "completed"
        assert events[1]["llm_review_binding_role"] == "review"
        assert events[1]["llm_review_pipeline_mode"] is True
        assert events[1]["llm_review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_success_true_when_no_error_and_has_result(self):
        """success returns True when no error and loop_result exists."""
        result = ReviewResult(
            loop_result=ReviewLoopResult(
                iterations=(),
                final_iteration=0,
                max_iterations=3,
                min_iterations=1,
                prev_digest="",
                curr_digest="",
                revision_delta="changed",
                completion_status=CompletionStatus.PHASE6_IN_PROGRESS,
                implementation_review_complete=False,
            ),
        )
        assert result.success is True

    def test_success_false_when_error(self):
        """success returns False when error is set."""
        result = ReviewResult(loop_result=None, error="Something went wrong")
        assert result.success is False

    def test_success_false_when_no_result(self):
        """success returns False when loop_result is None."""
        result = ReviewResult(loop_result=None)
        assert result.success is False

    def test_is_blocked_true(self):
        """is_blocked returns True when loop is blocked."""
        result = ReviewResult(
            loop_result=ReviewLoopResult(
                iterations=(),
                final_iteration=0,
                max_iterations=3,
                min_iterations=1,
                prev_digest="",
                curr_digest="",
                revision_delta="changed",
                completion_status=CompletionStatus.PHASE6_IN_PROGRESS,
                implementation_review_complete=False,
                blocked=True,
            ),
        )
        assert result.is_blocked is True

    def test_is_complete_true(self):
        """is_complete returns True when loop is complete."""
        result = ReviewResult(
            loop_result=ReviewLoopResult(
                iterations=(),
                final_iteration=3,
                max_iterations=3,
                min_iterations=1,
                prev_digest="a",
                curr_digest="a",
                revision_delta="none",
                completion_status=CompletionStatus.PHASE6_COMPLETED,
                implementation_review_complete=True,
            ),
        )
        assert result.is_complete is True
