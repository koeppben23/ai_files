"""Review result data structures for Phase-6 orchestrator.

These dataclasses represent the structured output of the review loop,
which the entrypoint applies to state and persists. The orchestrator
never mutates state directly - it returns these result objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReviewOutcome(str, Enum):
    """Outcome of a single review iteration."""

    COMPLETED = "completed"
    REVISED = "revised"


class CompletionStatus(str, Enum):
    """Overall completion status of the review loop.
    
    Note: These are internal enum values. The canonical Phase 6 state values
    (6.complete, 6.execution, etc.) are set in to_state_updates().
    """

    PHASE6_COMPLETED = "phase6-completed"
    PHASE6_IN_PROGRESS = "phase6-in-progress"


@dataclass(frozen=True)
class ReviewIteration:
    """Result of a single review iteration."""

    iteration: int
    input_digest: str
    output_digest: str
    revision_delta: str  # "none" or "changed"
    outcome: ReviewOutcome
    llm_invoked: bool
    llm_valid: bool
    llm_verdict: str  # "approve", "changes_requested", "unknown"
    llm_findings: list[str] = field(default_factory=list)
    llm_response_raw: str | None = None

    @property
    def is_complete(self) -> bool:
        """Check if this iteration represents a completed review."""
        return self.outcome == ReviewOutcome.COMPLETED


@dataclass(frozen=True)
class ReviewLoopResult:
    """Result of running the complete review loop."""

    iterations: tuple[ReviewIteration, ...]
    final_iteration: int
    max_iterations: int
    min_iterations: int
    prev_digest: str
    curr_digest: str
    revision_delta: str
    completion_status: CompletionStatus
    implementation_review_complete: bool
    blocked: bool = False
    block_reason: str | None = None
    block_reason_code: str | None = None
    recovery_action: str | None = None

    @property
    def is_complete(self) -> bool:
        """Check if the review loop completed successfully."""
        return self.completion_status == CompletionStatus.PHASE6_COMPLETED

    def to_state_updates(self) -> dict[str, Any]:
        """Convert result to state updates that entrypoint should apply.

        Returns a dict of state updates to be applied to SESSION_STATE.
        The entrypoint is responsible for persisting these updates.
        """
        if self.blocked:
            return {
                "phase6_blocker_code": self.block_reason_code or "unknown",
                "phase6_blocker_reason": self.block_reason,
                "phase6_recovery_action": self.recovery_action,
            }

        review_block = {
            "iteration": self.final_iteration,
            "max_iterations": self.max_iterations,
            "min_self_review_iterations": self.min_iterations,
            "prev_impl_digest": self.prev_digest,
            "curr_impl_digest": self.curr_digest,
            "revision_delta": self.revision_delta,
            "completion_status": self.completion_status.value,
            "implementation_review_complete": self.implementation_review_complete,
        }

        # Add LLM review data if available
        for it in self.iterations:
            review_block[f"llm_review_iteration_{it.iteration}"] = {
                "llm_invoked": it.llm_invoked,
                "validation_valid": it.llm_valid,
                "verdict": it.llm_verdict,
                "findings": it.llm_findings,
            }
        if self.iterations:
            last = self.iterations[-1]
            review_block["llm_review_valid"] = last.llm_valid
            review_block["llm_review_verdict"] = last.llm_verdict
            review_block["llm_review_findings"] = last.llm_findings

        return {
            "ImplementationReview": review_block,
            "phase6_review_iterations": self.final_iteration,
            "phase6_max_review_iterations": self.max_iterations,
            "phase6_min_self_review_iterations": self.min_iterations,
            "phase6_prev_impl_digest": self.prev_digest,
            "phase6_curr_impl_digest": self.curr_digest,
            "phase6_revision_delta": self.revision_delta,
            "implementation_review_complete": self.implementation_review_complete,
            "phase6_state": "6.complete" if self.is_complete else "6.execution",
            "phase6_blocker_code": "none",
        }

    def to_audit_events(self) -> list[dict[str, Any]]:
        """Convert iterations to audit event rows for persistence.

        The entrypoint is responsible for writing these to events.jsonl.
        """
        events = []
        for it in self.iterations:
            events.append({
                "event": "phase6-implementation-review-iteration",
                "iteration": it.iteration,
                "input_digest": it.input_digest,
                "revision_delta": it.revision_delta,
                "outcome": it.outcome.value,
                "completion_status": (
                    CompletionStatus.PHASE6_COMPLETED.value
                    if it.is_complete
                    else CompletionStatus.PHASE6_IN_PROGRESS.value
                ),
                "reason_code": "none",
                "impl_digest": it.output_digest,
                "llm_review_invoked": it.llm_invoked,
                "llm_review_valid": it.llm_valid,
                "llm_review_verdict": it.llm_verdict,
            })
        return events


@dataclass(frozen=True)
class ReviewResult:
    """Complete result of the Phase-6 review process.

    This is the top-level result returned by run_review_loop.
    It contains the loop result and any additional context.
    """

    loop_result: ReviewLoopResult | None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if the review completed without errors."""
        return self.error is None and self.loop_result is not None

    @property
    def is_blocked(self) -> bool:
        """Check if the review is blocked."""
        return self.loop_result is not None and self.loop_result.blocked

    @property
    def is_complete(self) -> bool:
        """Check if the review completed successfully."""
        return self.loop_result is not None and self.loop_result.is_complete
