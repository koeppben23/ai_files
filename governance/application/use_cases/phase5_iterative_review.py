"""Phase 5 Iterative Review Mechanism.

Implements a structured review cycle for implementation plans with:
- Maximum 3 iterations
- LLM self-critique review
- Optional human escalation
- Structured feedback format

Contract:
- Each review produces structured feedback (issues, suggestions, questions)
- If issues remain after 3 iterations, escalate to human
- Approved plans proceed to Phase 6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

ReviewStatus = Literal["approved", "rejected", "needs-human"]

MAX_REVIEW_ITERATIONS: int = 3


@dataclass(frozen=True)
class Phase5ReviewFeedback:
    """Structured feedback from a Phase 5 review iteration."""
    
    iteration: int
    issues: tuple[str, ...]          # Blocking - must be fixed
    suggestions: tuple[str, ...]     # Non-blocking - recommended improvements
    questions: tuple[str, ...]       # Questions for human review
    status: ReviewStatus
    summary: str = ""
    
    @property
    def has_blocking_issues(self) -> bool:
        return len(self.issues) > 0
    
    @property
    def needs_human_input(self) -> bool:
        return len(self.questions) > 0 or self.status == "needs-human"


@dataclass(frozen=True)
class Phase5ReviewState:
    """Tracks the state of iterative Phase 5 reviews."""
    
    iteration: int
    feedback_history: tuple[Phase5ReviewFeedback, ...]
    final_status: Literal["pending", "approved", "escalated-to-human"]
    plan_version: int = 1
    
    @property
    def can_iterate(self) -> bool:
        """Returns True if another review iteration is possible."""
        return self.iteration < MAX_REVIEW_ITERATIONS and self.final_status == "pending"
    
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


@dataclass(frozen=True)
class Phase5ReviewResult:
    """Result of a complete Phase 5 review cycle."""
    
    approved: bool
    escalated_to_human: bool
    iterations_used: int
    final_feedback: Phase5ReviewFeedback | None
    review_state: Phase5ReviewState
    escalation_reason: str | None = None


def create_initial_review_state() -> Phase5ReviewState:
    """Create a fresh Phase 5 review state."""
    return Phase5ReviewState(
        iteration=0,
        feedback_history=(),
        final_status="pending",
        plan_version=1,
    )


def record_review_feedback(
    state: Phase5ReviewState,
    *,
    issues: Sequence[str],
    suggestions: Sequence[str],
    questions: Sequence[str],
    summary: str = "",
) -> Phase5ReviewState:
    """Record feedback from a review iteration and determine next state."""
    
    new_iteration = min(state.iteration + 1, MAX_REVIEW_ITERATIONS)
    
    # Determine status based on feedback
    if not issues and not questions:
        status: ReviewStatus = "approved"
        final_status: Literal["pending", "approved", "escalated-to-human"] = "approved"
    elif questions and new_iteration >= MAX_REVIEW_ITERATIONS:
        status = "needs-human"
        final_status = "escalated-to-human"
    elif issues and new_iteration >= MAX_REVIEW_ITERATIONS:
        status = "rejected"
        final_status = "escalated-to-human"
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
    )
    
    return Phase5ReviewState(
        iteration=new_iteration,
        feedback_history=state.feedback_history + (feedback,),
        final_status=final_status,
        plan_version=state.plan_version,
    )


def increment_plan_version(state: Phase5ReviewState) -> Phase5ReviewState:
    """Increment plan version after addressing feedback."""
    return Phase5ReviewState(
        iteration=state.iteration,
        feedback_history=state.feedback_history,
        final_status=state.final_status,
        plan_version=state.plan_version + 1,
    )


def finalize_review(state: Phase5ReviewState) -> Phase5ReviewResult:
    """Finalize the review cycle and return the result."""
    
    final_feedback = state.current_feedback
    
    if state.final_status == "approved":
        return Phase5ReviewResult(
            approved=True,
            escalated_to_human=False,
            iterations_used=state.iteration,
            final_feedback=final_feedback,
            review_state=state,
            escalation_reason=None,
        )
    
    if state.final_status == "escalated-to-human":
        escalation_reason = _determine_escalation_reason(state)
        return Phase5ReviewResult(
            approved=False,
            escalated_to_human=True,
            iterations_used=state.iteration,
            final_feedback=final_feedback,
            review_state=state,
            escalation_reason=escalation_reason,
        )
    
    # Still pending but cannot iterate further
    if not state.can_iterate:
        return Phase5ReviewResult(
            approved=False,
            escalated_to_human=True,
            iterations_used=state.iteration,
            final_feedback=final_feedback,
            review_state=state,
            escalation_reason="Max iterations reached without approval",
        )
    
    # Still pending, can iterate
    return Phase5ReviewResult(
        approved=False,
        escalated_to_human=False,
        iterations_used=state.iteration,
        final_feedback=final_feedback,
        review_state=state,
        escalation_reason=None,
    )


def _determine_escalation_reason(state: Phase5ReviewState) -> str:
    """Determine why the review was escalated to human."""
    
    if not state.feedback_history:
        return "No feedback recorded"
    
    latest = state.feedback_history[-1]
    
    if latest.questions:
        return f"Open questions require human input: {', '.join(latest.questions[:3])}"
    
    if latest.issues:
        return f"Unresolved blocking issues after {state.iteration} iterations: {', '.join(latest.issues[:3])}"
    
    return f"Review not approved after {state.iteration} iterations"


def format_review_summary(state: Phase5ReviewState) -> str:
    """Format a human-readable summary of the review cycle."""
    
    lines = [
        f"## Phase 5 Review Summary",
        f"",
        f"- **Iterations:** {state.iteration}/{MAX_REVIEW_ITERATIONS}",
        f"- **Plan Versions:** {state.plan_version}",
        f"- **Status:** {state.final_status}",
        f"- **Total Issues Found:** {state.total_issues_found}",
        f"- **Total Suggestions:** {state.total_suggestions_found}",
    ]
    
    if state.feedback_history:
        lines.append("")
        lines.append("### Feedback History")
        
        for fb in state.feedback_history:
            lines.append(f"")
            lines.append(f"**Iteration {fb.iteration}:** `{fb.status}`")
            
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
