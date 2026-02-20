"""Phase 5 Iterative Review Mechanism.

Enterprise-grade iterative review for implementation plans:
- Configurable max iterations (SSOT from YAML)
- Operating mode aware (user/pipeline/agents_strict)
- Pipeline mode: NO human interaction
- Structured feedback with audit trail
- Review criteria validation

Contract:
- Each review produces structured feedback (issues, suggestions, questions)
- Pipeline mode: auto-reject on blocking issues, no escalation
- User mode: escalate to human after max iterations
- Approved plans proceed to Phase 6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence, Any

from governance.application.use_cases.phase5_review_config import (
    OperatingMode,
    Phase5ReviewConfig,
    load_phase5_review_config,
    get_max_iterations,
    is_human_escalation_enabled,
    is_fail_fast_enabled,
)


ReviewStatus = Literal["approved", "rejected", "needs-human"]
FinalStatus = Literal["pending", "approved", "escalated-to-human", "rejected-no-human"]


@dataclass(frozen=True)
class Phase5ReviewFeedback:
    """Structured feedback from a Phase 5 review iteration."""
    
    iteration: int
    issues: tuple[str, ...]          # Blocking - must be fixed
    suggestions: tuple[str, ...]     # Non-blocking - recommended improvements
    questions: tuple[str, ...]       # Questions for human review
    status: ReviewStatus
    summary: str = ""
    timestamp: str = ""              # Injected from infrastructure layer
    criteria_results: dict[str, bool] = field(default_factory=dict)
    
    @property
    def has_blocking_issues(self) -> bool:
        return len(self.issues) > 0
    
    @property
    def needs_human_input(self) -> bool:
        return len(self.questions) > 0 or self.status == "needs-human"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "issues": list(self.issues),
            "suggestions": list(self.suggestions),
            "questions": list(self.questions),
            "status": self.status,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "criteria_results": self.criteria_results,
        }


@dataclass(frozen=True)
class Phase5ReviewState:
    """Tracks the state of iterative Phase 5 reviews."""
    
    iteration: int
    feedback_history: tuple[Phase5ReviewFeedback, ...]
    final_status: FinalStatus
    plan_version: int = 1
    operating_mode: OperatingMode = "user"
    started_at: str = ""              # Injected from infrastructure layer
    completed_at: str = ""            # Injected from infrastructure layer
    
    @property
    def max_iterations(self) -> int:
        """Get max iterations from config (SSOT)."""
        return get_max_iterations(self.operating_mode)
    
    @property
    def can_iterate(self) -> bool:
        """Returns True if another review iteration is possible."""
        return (
            self.iteration < self.max_iterations 
            and self.final_status == "pending"
        )
    
    @property
    def current_feedback(self) -> Phase5ReviewFeedback | None:
        """Returns the most recent feedback, if any."""
        if self.feedback_history:
            return self.feedback_history[-1]
        return None
    
    @property
    def total_issues_found(self) -> int:
        """Total number of issues across all iterations."""
        return sum(len(fb.issues) for fb in self.feedback_history)
    
    @property
    def total_suggestions_found(self) -> int:
        """Total number of suggestions across all iterations."""
        return sum(len(fb.suggestions) for fb in self.feedback_history)
    
    @property
    def human_escalation_enabled(self) -> bool:
        """Check if human escalation is enabled for current mode."""
        return is_human_escalation_enabled(self.operating_mode)
    
    @property
    def fail_fast_enabled(self) -> bool:
        """Check if fail-fast is enabled for current mode."""
        return is_fail_fast_enabled(self.operating_mode)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize state for SESSION_STATE persistence."""
        return {
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "plan_version": self.plan_version,
            "operating_mode": self.operating_mode,
            "final_status": self.final_status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "feedback_history": [fb.to_dict() for fb in self.feedback_history],
            "total_issues_found": self.total_issues_found,
            "total_suggestions_found": self.total_suggestions_found,
            "human_escalation_enabled": self.human_escalation_enabled,
        }


@dataclass(frozen=True)
class Phase5ReviewResult:
    """Result of a complete Phase 5 review cycle."""
    
    approved: bool
    escalated_to_human: bool
    rejected_no_human: bool  # True in pipeline mode when would escalate
    iterations_used: int
    final_feedback: Phase5ReviewFeedback | None
    review_state: Phase5ReviewState
    escalation_reason: str | None = None
    rejection_reason: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "escalated_to_human": self.escalated_to_human,
            "rejected_no_human": self.rejected_no_human,
            "iterations_used": self.iterations_used,
            "escalation_reason": self.escalation_reason,
            "rejection_reason": self.rejection_reason,
            "final_feedback": self.final_feedback.to_dict() if self.final_feedback else None,
        }


def create_initial_review_state(
    operating_mode: OperatingMode = "user",
) -> Phase5ReviewState:
    """Create a fresh Phase 5 review state."""
    return Phase5ReviewState(
        iteration=0,
        feedback_history=(),
        final_status="pending",
        plan_version=1,
        operating_mode=operating_mode,
    )


def record_review_feedback(
    state: Phase5ReviewState,
    *,
    issues: Sequence[str],
    suggestions: Sequence[str],
    questions: Sequence[str],
    summary: str = "",
    criteria_results: dict[str, bool] | None = None,
    timestamp: str = "",
    completed_at: str = "",
) -> Phase5ReviewState:
    """Record feedback from a review iteration and determine next state.
    
    Behavior depends on operating mode:
    - user: Escalate to human after max iterations
    - pipeline: Reject immediately (no human escalation)
    - agents_strict: Single iteration, no auto-approve
    
    Timestamps should be injected from infrastructure layer.
    """
    config = load_phase5_review_config()
    mode_config = config.get_mode_config(state.operating_mode)
    max_iter = mode_config.max_iterations
    
    new_iteration = min(state.iteration + 1, max_iter)
    
    # Determine status based on feedback and mode
    status: ReviewStatus
    final_status: FinalStatus
    
    if not issues and not questions:
        # No blocking issues
        if mode_config.auto_approve_on_no_issues:
            status = "approved"
            final_status = "approved"
        else:
            # agents_strict mode - requires explicit approval
            status = "rejected"
            final_status = "pending"
    elif questions and new_iteration >= max_iter:
        # Questions remain at max iterations
        status = "needs-human"
        if mode_config.human_escalation_enabled:
            final_status = "escalated-to-human"
        else:
            # Pipeline mode: no human, so reject
            final_status = "rejected-no-human"
    elif issues and new_iteration >= max_iter:
        # Issues remain at max iterations
        status = "rejected"
        if mode_config.human_escalation_enabled:
            final_status = "escalated-to-human"
        else:
            final_status = "rejected-no-human"
    elif issues and mode_config.fail_fast and mode_config.auto_reject_on_blocking_issues:
        # Fail-fast mode: reject immediately on blocking issues
        status = "rejected"
        final_status = "rejected-no-human"
    else:
        status = "rejected"
        final_status = "pending"
    
    feedback = Phase5ReviewFeedback(
        iteration=new_iteration,
        issues=tuple(issues),
        suggestions=tuple(suggestions),
        questions=tuple(questions),
        status=status,
        summary=summary,
        timestamp=timestamp,
        criteria_results=criteria_results or {},
    )
    
    final_completed_at = completed_at
    if not final_completed_at and final_status in ("approved", "escalated-to-human", "rejected-no-human"):
        # Infrastructure layer should provide this, but empty is valid
        final_completed_at = ""
    
    return Phase5ReviewState(
        iteration=new_iteration,
        feedback_history=state.feedback_history + (feedback,),
        final_status=final_status,
        plan_version=state.plan_version,
        operating_mode=state.operating_mode,
        started_at=state.started_at,
        completed_at=final_completed_at,
    )


def increment_plan_version(state: Phase5ReviewState) -> Phase5ReviewState:
    """Increment plan version after addressing feedback."""
    return Phase5ReviewState(
        iteration=state.iteration,
        feedback_history=state.feedback_history,
        final_status=state.final_status,
        plan_version=state.plan_version + 1,
        operating_mode=state.operating_mode,
        started_at=state.started_at,
        completed_at=state.completed_at,
    )


def finalize_review(state: Phase5ReviewState) -> Phase5ReviewResult:
    """Finalize the review cycle and return the result.
    
    Returns different results based on operating mode:
    - approved: Plan is approved, proceed to Phase 6
    - escalated_to_human: User mode - needs human review
    - rejected_no_human: Pipeline mode - rejected, no human available
    """
    final_feedback = state.current_feedback
    
    if state.final_status == "approved":
        return Phase5ReviewResult(
            approved=True,
            escalated_to_human=False,
            rejected_no_human=False,
            iterations_used=state.iteration,
            final_feedback=final_feedback,
            review_state=state,
        )
    
    if state.final_status == "escalated-to-human":
        escalation_reason = _determine_escalation_reason(state)
        return Phase5ReviewResult(
            approved=False,
            escalated_to_human=True,
            rejected_no_human=False,
            iterations_used=state.iteration,
            final_feedback=final_feedback,
            review_state=state,
            escalation_reason=escalation_reason,
        )
    
    if state.final_status == "rejected-no-human":
        rejection_reason = _determine_rejection_reason(state)
        return Phase5ReviewResult(
            approved=False,
            escalated_to_human=False,
            rejected_no_human=True,
            iterations_used=state.iteration,
            final_feedback=final_feedback,
            review_state=state,
            rejection_reason=rejection_reason,
        )
    
    # Still pending but cannot iterate further
    if not state.can_iterate:
        if state.human_escalation_enabled:
            escalation_reason = _determine_escalation_reason(state)
            return Phase5ReviewResult(
                approved=False,
                escalated_to_human=True,
                rejected_no_human=False,
                iterations_used=state.iteration,
                final_feedback=final_feedback,
                review_state=state,
                escalation_reason=escalation_reason,
            )
        else:
            return Phase5ReviewResult(
                approved=False,
                escalated_to_human=False,
                rejected_no_human=True,
                iterations_used=state.iteration,
                final_feedback=final_feedback,
                review_state=state,
                rejection_reason="Max iterations reached without approval (pipeline mode)",
            )
    
    # Still pending, can iterate
    return Phase5ReviewResult(
        approved=False,
        escalated_to_human=False,
        rejected_no_human=False,
        iterations_used=state.iteration,
        final_feedback=final_feedback,
        review_state=state,
    )


def _determine_escalation_reason(state: Phase5ReviewState) -> str:
    """Determine why the review was escalated to human (user mode)."""
    if not state.feedback_history:
        return "No feedback recorded"
    
    latest = state.feedback_history[-1]
    
    if latest.questions:
        return f"Open questions require human input: {', '.join(latest.questions[:3])}"
    
    if latest.issues:
        return f"Unresolved blocking issues after {state.iteration} iterations: {', '.join(latest.issues[:3])}"
    
    return f"Review not approved after {state.iteration} iterations"


def _determine_rejection_reason(state: Phase5ReviewState) -> str:
    """Determine why the review was rejected in pipeline mode."""
    if not state.feedback_history:
        return "No feedback recorded"
    
    latest = state.feedback_history[-1]
    
    if state.fail_fast_enabled and latest.issues:
        return f"Fail-fast: Blocking issue detected: {latest.issues[0]}"
    
    if latest.issues:
        return f"Unresolved blocking issues after {state.iteration} iterations: {', '.join(latest.issues[:3])}"
    
    if latest.questions:
        return f"Open questions cannot be resolved in pipeline mode: {', '.join(latest.questions[:3])}"
    
    return f"Review not approved after {state.iteration} iterations (pipeline mode)"


def format_review_summary(state: Phase5ReviewState) -> str:
    """Format a human-readable summary of the review cycle."""
    
    lines = [
        "## Phase 5 Review Summary",
        "",
        f"- **Operating Mode:** {state.operating_mode}",
        f"- **Iterations:** {state.iteration}/{state.max_iterations}",
        f"- **Plan Versions:** {state.plan_version}",
        f"- **Status:** {state.final_status}",
        f"- **Total Issues Found:** {state.total_issues_found}",
        f"- **Total Suggestions:** {state.total_suggestions_found}",
        f"- **Human Escalation:** {'Enabled' if state.human_escalation_enabled else 'Disabled (pipeline mode)'}",
    ]
    
    if state.feedback_history:
        lines.append("")
        lines.append("### Feedback History")
        
        for fb in state.feedback_history:
            lines.append("")
            lines.append(f"**Iteration {fb.iteration}:** `{fb.status}` ({fb.timestamp})")
            
            if fb.criteria_results:
                passed = sum(1 for v in fb.criteria_results.values() if v)
                total = len(fb.criteria_results)
                lines.append(f"- **Criteria:** {passed}/{total} passed")
            
            if fb.issues:
                lines.append(f"- **Issues:** {len(fb.issues)}")
                for issue in fb.issues[:3]:
                    lines.append(f"  - {issue}")
            
            if fb.suggestions:
                lines.append(f"- **Suggestions:** {len(fb.suggestions)}")
                for sug in fb.suggestions[:3]:
                    lines.append(f"  - {sug}")
            
            if fb.questions:
                lines.append(f"- **Questions:** {len(fb.questions)}")
                for q in fb.questions[:3]:
                    lines.append(f"  - {q}")
    
    return "\n".join(lines)


def validate_review_criteria(
    state: Phase5ReviewState,
    *,
    test_coverage_percent: int | None = None,
    security_scan_passed: bool | None = None,
    architecture_doc_present: bool | None = None,
    breaking_changes_documented: bool | None = None,
    rollback_plan_present: bool | None = None,
) -> dict[str, bool]:
    """Validate review criteria and return results.
    
    Returns dict of criterion -> passed (True/False).
    Missing inputs are treated as not applicable (True).
    """
    config = load_phase5_review_config()
    criteria = config.criteria
    
    results: dict[str, bool] = {}
    
    if test_coverage_percent is not None:
        results["test_coverage"] = test_coverage_percent >= criteria.test_coverage_min_percent
    else:
        results["test_coverage"] = True  # N/A
    
    if security_scan_passed is not None:
        results["security_scan"] = security_scan_passed if criteria.security_scan_required else True
    else:
        results["security_scan"] = True
    
    if architecture_doc_present is not None:
        results["architecture_doc"] = architecture_doc_present if criteria.architecture_doc_required else True
    else:
        results["architecture_doc"] = True
    
    if breaking_changes_documented is not None:
        results["breaking_changes"] = breaking_changes_documented if criteria.breaking_changes_documented else True
    else:
        results["breaking_changes"] = True
    
    if rollback_plan_present is not None:
        results["rollback_plan"] = rollback_plan_present if criteria.rollback_plan_required else True
    else:
        results["rollback_plan"] = True
    
    return results


def get_criteria_failures(criteria_results: dict[str, bool]) -> list[str]:
    """Get list of failed criteria as human-readable strings."""
    failures = []
    
    if not criteria_results.get("test_coverage", True):
        failures.append("Test coverage below required minimum")
    if not criteria_results.get("security_scan", True):
        failures.append("Security scan not passed")
    if not criteria_results.get("architecture_doc", True):
        failures.append("Architecture documentation missing")
    if not criteria_results.get("breaking_changes", True):
        failures.append("Breaking changes not documented")
    if not criteria_results.get("rollback_plan", True):
        failures.append("Rollback plan missing")
    
    return failures
