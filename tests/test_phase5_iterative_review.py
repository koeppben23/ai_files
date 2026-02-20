"""Tests for Phase 5 Iterative Review Mechanism - Enterprise Edition."""

from __future__ import annotations

import pytest

from governance.application.use_cases.phase5_iterative_review import (
    Phase5ReviewFeedback,
    Phase5ReviewResult,
    Phase5ReviewState,
    create_initial_review_state,
    finalize_review,
    format_review_summary,
    get_criteria_failures,
    increment_plan_version,
    record_review_feedback,
    validate_review_criteria,
)
from governance.application.use_cases.phase5_review_config import (
    get_max_iterations,
    is_human_escalation_enabled,
    is_fail_fast_enabled,
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

    def test_timestamp_can_be_provided(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=(),
            suggestions=(),
            questions=(),
            status="approved",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert feedback.timestamp == "2026-01-01T00:00:00Z"

    def test_timestamp_defaults_to_empty(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=(),
            suggestions=(),
            questions=(),
            status="approved",
        )
        assert feedback.timestamp == ""

    def test_to_dict_serializes_correctly(self):
        feedback = Phase5ReviewFeedback(
            iteration=1,
            issues=("Issue 1",),
            suggestions=("Suggestion 1",),
            questions=(),
            status="rejected",
            summary="Test summary",
        )
        d = feedback.to_dict()
        assert d["iteration"] == 1
        assert d["issues"] == ["Issue 1"]
        assert d["suggestions"] == ["Suggestion 1"]
        assert d["status"] == "rejected"


@pytest.mark.governance
class TestPhase5ReviewStateUserMode:
    """Tests for Phase5ReviewState in USER mode (human escalation enabled)."""

    def test_can_iterate_when_at_zero(self):
        state = create_initial_review_state(operating_mode="user")
        assert state.can_iterate is True

    def test_can_iterate_when_below_max(self):
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(),
            final_status="pending",
            operating_mode="user",
        )
        assert state.can_iterate is True

    def test_cannot_iterate_when_at_max(self):
        state = Phase5ReviewState(
            iteration=3,
            feedback_history=(),
            final_status="pending",
            operating_mode="user",
        )
        assert state.can_iterate is False

    def test_human_escalation_enabled_in_user_mode(self):
        state = create_initial_review_state(operating_mode="user")
        assert state.human_escalation_enabled is True

    def test_fail_fast_disabled_in_user_mode(self):
        state = create_initial_review_state(operating_mode="user")
        assert state.fail_fast_enabled is False

    def test_escalates_to_human_after_max_iterations(self):
        state = create_initial_review_state(operating_mode="user")
        
        state = record_review_feedback(state, issues=["Issue 1"], suggestions=[], questions=[])
        state = record_review_feedback(state, issues=["Issue 2"], suggestions=[], questions=[])
        state = record_review_feedback(state, issues=["Issue 3"], suggestions=[], questions=[])
        
        assert state.final_status == "escalated-to-human"

    def test_approves_when_no_issues(self):
        state = create_initial_review_state(operating_mode="user")
        state = record_review_feedback(state, issues=[], suggestions=[], questions=[])
        
        assert state.final_status == "approved"


@pytest.mark.governance
class TestPhase5ReviewStatePipelineMode:
    """Tests for Phase5ReviewState in PIPELINE mode (NO human interaction)."""

    def test_human_escalation_disabled_in_pipeline_mode(self):
        state = create_initial_review_state(operating_mode="pipeline")
        assert state.human_escalation_enabled is False

    def test_fail_fast_enabled_in_pipeline_mode(self):
        state = create_initial_review_state(operating_mode="pipeline")
        assert state.fail_fast_enabled is True

    def test_rejects_immediately_on_blocking_issues(self):
        state = create_initial_review_state(operating_mode="pipeline")
        state = record_review_feedback(
            state, 
            issues=["Critical bug"], 
            suggestions=[], 
            questions=[]
        )
        
        assert state.final_status == "rejected-no-human"
        
        result = finalize_review(state)
        assert result.approved is False
        assert result.escalated_to_human is False
        assert result.rejected_no_human is True

    def test_no_human_escalation_at_max_iterations(self):
        state = Phase5ReviewState(
            iteration=2,
            feedback_history=(),
            final_status="pending",
            operating_mode="pipeline",
        )
        
        state = record_review_feedback(
            state,
            issues=[],
            suggestions=[],
            questions=["What about X?"],
        )
        
        assert state.final_status == "rejected-no-human"

    def test_approves_when_no_issues(self):
        state = create_initial_review_state(operating_mode="pipeline")
        state = record_review_feedback(state, issues=[], suggestions=[], questions=[])
        
        assert state.final_status == "approved"


@pytest.mark.governance
class TestPhase5ReviewStateAgentsStrictMode:
    """Tests for Phase5ReviewState in AGENTS_STRICT mode."""

    def test_no_auto_approve_in_agents_strict(self):
        state = create_initial_review_state(operating_mode="agents_strict")
        state = record_review_feedback(state, issues=[], suggestions=[], questions=[])
        
        assert state.final_status == "pending"

    def test_max_iterations_is_one_in_agents_strict(self):
        state = create_initial_review_state(operating_mode="agents_strict")
        assert state.max_iterations == 1


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
            operating_mode="user",
        )
        result = finalize_review(state)
        
        assert result.approved is True
        assert result.escalated_to_human is False
        assert result.rejected_no_human is False

    def test_escalated_state_returns_escalated_result_user_mode(self):
        fb = Phase5ReviewFeedback(
            iteration=3, issues=("Unresolved",), suggestions=(), questions=(), status="rejected"
        )
        state = Phase5ReviewState(
            iteration=3,
            feedback_history=(fb,),
            final_status="escalated-to-human",
            operating_mode="user",
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.escalated_to_human is True
        assert result.rejected_no_human is False
        assert result.escalation_reason is not None

    def test_rejected_no_human_in_pipeline_mode(self):
        fb = Phase5ReviewFeedback(
            iteration=1, issues=("Critical",), suggestions=(), questions=(), status="rejected"
        )
        state = Phase5ReviewState(
            iteration=1,
            feedback_history=(fb,),
            final_status="rejected-no-human",
            operating_mode="pipeline",
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.escalated_to_human is False
        assert result.rejected_no_human is True
        assert result.rejection_reason is not None


@pytest.mark.governance
class TestValidateReviewCriteria:
    """Tests for review criteria validation."""

    def test_all_criteria_pass(self):
        state = create_initial_review_state()
        results = validate_review_criteria(
            state,
            test_coverage_percent=85,
            security_scan_passed=True,
            architecture_doc_present=True,
            breaking_changes_documented=True,
            rollback_plan_present=True,
        )
        
        assert all(results.values())

    def test_fails_on_low_test_coverage(self):
        state = create_initial_review_state()
        results = validate_review_criteria(
            state,
            test_coverage_percent=50,
        )
        
        assert results["test_coverage"] is False

    def test_fails_on_security_scan_not_passed(self):
        state = create_initial_review_state()
        results = validate_review_criteria(
            state,
            security_scan_passed=False,
        )
        
        assert results["security_scan"] is False

    def test_missing_inputs_treated_as_na(self):
        state = create_initial_review_state()
        results = validate_review_criteria(state)
        
        assert all(results.values())


@pytest.mark.governance
class TestGetCriteriaFailures:
    """Tests for get_criteria_failures helper."""

    def test_returns_empty_list_when_all_pass(self):
        results = {"test_coverage": True, "security_scan": True}
        failures = get_criteria_failures(results)
        assert failures == []

    def test_returns_failure_messages(self):
        results = {
            "test_coverage": False,
            "security_scan": False,
            "architecture_doc": True,
        }
        failures = get_criteria_failures(results)
        
        assert len(failures) == 2
        assert any("Test coverage" in f for f in failures)
        assert any("Security scan" in f for f in failures)


@pytest.mark.governance
class TestFullReviewCycles:
    """Integration tests for complete review cycles in different modes."""

    def test_user_mode_approve_after_fixes(self):
        state = create_initial_review_state(operating_mode="user")
        
        state = record_review_feedback(
            state,
            issues=["Missing tests"],
            suggestions=["Add unit tests"],
            questions=[]
        )
        assert state.final_status == "pending"
        
        state = increment_plan_version(state)
        
        state = record_review_feedback(state, issues=[], suggestions=[], questions=[])
        result = finalize_review(state)
        
        assert result.approved is True
        assert result.iterations_used == 2
        assert result.review_state.plan_version == 2

    def test_pipeline_mode_fail_fast(self):
        state = create_initial_review_state(operating_mode="pipeline")
        
        state = record_review_feedback(
            state,
            issues=["Security vulnerability"],
            suggestions=[],
            questions=[]
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.rejected_no_human is True
        assert result.iterations_used == 1
        if result.rejection_reason:
            assert "Fail-fast" in result.rejection_reason

    def test_pipeline_mode_with_questions_rejects(self):
        """Pipeline mode: questions cannot be resolved, must reject."""
        state = create_initial_review_state(operating_mode="pipeline")
        
        # First 2 iterations with issues to build up to max
        state = record_review_feedback(
            state,
            issues=["Issue 1"],
            suggestions=[],
            questions=[]
        )
        state = record_review_feedback(
            state,
            issues=["Issue 2"],
            suggestions=[],
            questions=[]
        )
        # Third iteration with questions - should reject
        state = record_review_feedback(
            state,
            issues=[],
            suggestions=[],
            questions=["Which database?"]
        )
        result = finalize_review(state)
        
        assert result.approved is False
        assert result.rejected_no_human is True

    def test_state_serialization(self):
        state = create_initial_review_state(operating_mode="user")
        state = record_review_feedback(
            state,
            issues=["Issue 1"],
            suggestions=["Suggestion 1"],
            questions=[]
        )
        
        d = state.to_dict()
        
        assert "iteration" in d
        assert "max_iterations" in d
        assert "operating_mode" in d
        assert "feedback_history" in d
        assert "human_escalation_enabled" in d
        assert d["operating_mode"] == "user"


@pytest.mark.governance
class TestFormatReviewSummary:
    """Tests for format_review_summary function."""

    def test_includes_operating_mode(self):
        state = create_initial_review_state(operating_mode="pipeline")
        summary = format_review_summary(state)
        
        assert "pipeline" in summary

    def test_includes_human_escalation_status(self):
        state = create_initial_review_state(operating_mode="pipeline")
        summary = format_review_summary(state)
        
        assert "Disabled" in summary or "pipeline mode" in summary
