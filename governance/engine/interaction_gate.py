"""Global interaction gate for deterministic non-interactive enforcement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InteractionGateDecision:
    blocked: bool
    event: dict[str, object] | None


def evaluate_interaction_gate(
    *,
    effective_mode: str,
    interactive_required: bool,
    prompt_used_total: int,
    prompt_used_repo_docs: int,
    requested_action: str,
) -> InteractionGateDecision:
    """Block any prompt attempt in pipeline mode."""

    prompt_attempted = interactive_required or prompt_used_total > 0 or prompt_used_repo_docs > 0
    if effective_mode != "pipeline" or not prompt_attempted:
        return InteractionGateDecision(blocked=False, event=None)

    source = "repo_docs" if prompt_used_repo_docs > 0 else "governance"
    topic = requested_action.strip() if isinstance(requested_action, str) and requested_action.strip() else "interactive_required"
    return InteractionGateDecision(
        blocked=True,
        event={
            "event": "PROMPT_REQUESTED",
            "source": source,
            "topic": topic,
            "mode": effective_mode,
        },
    )
