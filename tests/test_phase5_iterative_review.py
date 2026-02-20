"""Tests for Phase 5 Iterative Review Mechanism."""

from __future__ import annotations

import pytest

from governance.application.use_cases.phase5_iterative_review import (
    MAX_REVIEW_ITERATIONS,
    Phase5ReviewFeedback,
    Phase5ReviewResult,
    Phase5ReviewState,
    create_initial_review_state,
    finalize_review,
    format_review_summary,
    increment_plan_version,
    record_review_feedback,
)


@pytest.mark.governance
class TestPhase5ReviewFeedback:
    """Tests for Phase5ReviewFeedback dataclass."""

    def test_has_blocking_issues_when_issues_exist(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=("Missing test coverage", "No error handling"),
            suggestions=(),
            questions=(),
            status="rejected",
        )
        assert feedback.has_blocking_issues is True

    def test_has_no_blocking_issues_when_empty(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=(),
            suggestions=("Consider caching",),
            questions=(),
            status="approved",
        )
        assert feedback.has_blocking_issues is False

    def test_needs_human_input_when_questions_exist(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=(),
            suggestions=(),
            questions=("Should we use async?",),
            status="rejected",
        )
        assert feedback.needs_human_input is True

    def test_needs_human_input_when_status_is_needs_human(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=(),
            suggestions=(),
            questions=(),
            status="needs-human",
        )
        assert feedback.needs_human_input is True


@pytest.mark.governance
class TestPhase5ReviewState:
    """Tests for Phase5ReviewState dataclass."""

    def test_can_iterate_when_at_zero(self):
        state = create_initial_review_state()
        assert state.can_iterate is True

    def test_can_iterate_when_below_max(self):
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(),
            final_status="pending",
        )
        assert state.can_iterate is True

    def test_cannot_iterate_when_at_max(self):
        state = Phase5ReviewState(
            iteration=3,
            feedback_history=(),
            final_status="pending",
        )
        assert state.can_iterate is False

    def test_cannot_iterate_when_approved(self):
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(),
            final_status="approved",
        )
        assert state.can_iterate is False

    def test_current_feedback_returns_none_when_empty(self):
        state = create_initial_review_state()
        assert state.current_feedback is None

    def test_current_feedback_returns_latest(self):
        fb1 = Phase5ReviewFeedback(
            iteration=1, issues=(), suggestions=(), questions=(), status="rejected"
        )
        fb2 = Phase5ReviewFeedback(
            iteration=2, issues=(), suggestions=(), questions=(), status="approved"
        )
        state = Phase5ReviewState(
            iteration=2,
            feedback_history=(fb1, fb2),
            final_status="approved",
        )
        assert state.current_feedback == fb2

    def test_total_issues_found_aggregates(self):
        fb1 = Phase5ReviewFeedback(
            iteration=1, issues=("a", "b"), suggestions=(), questions=(), status="rejected"
        )
        fb2 = Phase5ReviewFeedback(
            iteration=2, issues=("c",), suggestions=(), questions=(), status="rejected"
        )
        state = Phase5ReviewState(
            iteration=2,
            feedback_history=(fb1, fb2),
            final_status="pending",
        )
        assert state.total_issues_found == 3


@pytest.mark.governance
class TestRecordReviewFeedback:
    """Tests for record_review_feedback function."""

    def test_first_feedback_sets_iteration_1(self):
        state = create_initial_review_state()
        new_state = record_review_feedback(
            state,
            issues=[],
            suggestions=[],
            questions=[],
        )
        assert new_state.iteration == 1

    def test_no_issues_no_questions_approves(self):
        state = create_initial_review_state()
        new_state = record_review_feedback(
            state,
            issues=[],
            suggestions=["Consider adding caching"],
            questions=[],
        )
        assert new_state.final_status == "approved"
        assert new_state.current_feedback.status == "approved"

    def test_issues_cause_rejection(self):
        state = create_initial_review_state()
        new_state = record_review_feedback(
            state,
            issues=["Missing tests"],
            suggestions=[],
            questions=[],
        )
        assert new_state.final_status == "pending"
        assert new_state.current_feedback.status == "rejected"

    def test_max_iterations_with_issues_escalates(self):
        # Start at iteration 2 (one below max)
        state = Phase5ReviewState(
            iteration=2,
            feedback_history=(),
            final_status="pending",
        )
        new_state = record_review_feedback(
            state,
            issues=["Still has issues"],
            suggestions=[],
            questions=[],
        )
        assert new_state.iteration == 3
        assert new_state.final_status == "escalated-to-human"

    def test_questions_at_max_iterations_escalates(self):
        state = Phase5ReviewState(
            iteration=2,
            feedback_history=(),
            final_status="pending",
        )
        new_state = record_review_feedback(
            state,
            issues=[],
            suggestions=[],
            questions=["What about edge cases?"],
        )
        assert new_state.final_status == "escalated-to-human"
        assert new_state.current_feedback.status == "needs-human"


@pytest.mark.governance
class TestIncrementPlanVersion:
    """Tests for increment_plan_version function."""

    def test_increments_plan_version(self):
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(),
            final_status="pending",
            plan_version=1,
        )
        new_state = increment_plan_version(state)
        assert new_state.plan_version == 2

    def test_preserves_other_state(self):
        fb = Phase5ReviewFeedback(
            iteration=1, issues=("x",), suggestions=(), questions=(), status="rejected"
        )
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(fb,),
            final_status="pending",
            plan_version=1,
        )
        new_state = increment_plan_version(state)
        assert new_state.iteration == 1
        assert new_state.feedback_history == (fb,)
        assert new_state.final_status == "pending"


@pytest.mark.governance
class TestFinalizeReview:
    """Tests for finalize_review function."""

    def test_approved_state_returns_approved_result(self):
        fb = Phase5ReviewFeedback(
            iteration=1, issues=(), suggestions=(), questions=(), status="approved"
        )
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(fb,),
            final_status="approved",
        )
        result = finalize_review(state)
        
        assert result.approved is True
        assert result.escalated_to_human is False
        assert result.iterations_used == 1
        assert result.final_feedback == fb

    def test_escalated_state_returns_escalated_result(self):
        fb = Phase5ReviewFeedback(
            iteration=3, issues=("Unresolved",), suggestions=(), questions=(), status="rejected"
        )
        state = Phase5ReviewState(
            iteration=3,
            feedback_history=(fb,),
            final_status="escalated-to-human",
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.escalated_to_human is True
        assert result.escalation_reason is not None
        assert "Unresolved" in result.escalation_reason

    def test_pending_at_max_iterations_escalates(self):
        state = Phase5ReviewState(
            iteration=3,
            feedback_history=(),
            final_status="pending",
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.escalated_to_human is True
        assert "Max iterations" in result.escalation_reason

    def test_pending_can_iterate_returns_pending_result(self):
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(),
            final_status="pending",
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.escalated_to_human is False


@pytest.mark.governance
class TestFormatReviewSummary:
    """Tests for format_review_summary function."""

    def test_formats_basic_summary(self):
        state = create_initial_review_state()
        summary = format_review_summary(state)
        
        assert "Phase 5 Review Summary" in summary
        assert "**Iterations:** 0" in summary
        assert f"/{MAX_REVIEW_ITERATIONS}" in summary

    def test_includes_feedback_history(self):
        fb = Phase5ReviewFeedback(
            iteration=1,
            issues=("Issue 1", "Issue 2"),
            suggestions=("Suggestion 1",),
            questions=("Question 1",),
            status="rejected",
        )
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(fb,),
            final_status="pending",
        )
        summary = format_review_summary(state)
        
        assert "Iteration 1" in summary
        assert "**Issues:** 2" in summary
        assert "Issue 1" in summary
        assert "**Suggestions:** 1" in summary
        assert "**Questions:** 1" in summary


@pytest.mark.governance
class TestFullReviewCycle:
    """Integration tests for complete review cycles."""

    def test_approve_on_first_iteration(self):
        """Plan is approved on first review."""
        state = create_initial_review_state()
        
        # Review 1: No issues
        state = record_review_feedback(state, issues=[], suggestions=[], questions=[])
        result = finalize_review(state)
        
        assert result.approved is True
        assert result.iterations_used == 1

    def test_approve_after_fixes(self):
        """Plan is approved after fixing issues from first review."""
        state = create_initial_review_state()
        
        # Review 1: Has issues
        state = record_review_feedback(
            state, 
            issues=["Missing tests"], 
            suggestions=["Add unit tests"], 
            questions=[]
        )
        assert state.final_status == "pending"
        
        # Fix plan
        state = increment_plan_version(state)
        
        # Review 2: Issues fixed
        state = record_review_feedback(state, issues=[], suggestions=[], questions=[])
        result = finalize_review(state)
        
        assert result.approved is True
        assert result.iterations_used == 2
        assert result.review_state.plan_version == 2

    def test_escalate_after_three_rejections(self):
        """Plan is escalated after 3 failed reviews."""
        state = create_initial_review_state()
        
        # Review 1: Issues
        state = record_review_feedback(
            state, issues=["Issue 1"], suggestions=[], questions=[]
        )
        
        # Review 2: Still issues
        state = record_review_feedback(
            state, issues=["Issue 2"], suggestions=[], questions=[]
        )
        
        # Review 3: Still issues - should escalate
        state = record_review_feedback(
            state, issues=["Issue 3"], suggestions=[], questions=[]
        )
        
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.escalated_to_human is True
        assert result.iterations_used == 3

    def test_escalate_with_open_questions_at_max(self):
        """Plan is escalated when questions remain at max iterations."""
        state = Phase5ReviewState(
            iteration=2,
            feedback_history=(),
            final_status="pending",
        )
        
        # Review 3: Has questions
        state = record_review_feedback(
            state, issues=[], suggestions=[], questions=["What about X?"]
        )
        
        result = finalize_review(state)
        
        assert result.escalated_to_human is True
        assert "human input" in result.escalation_reason.lower()
