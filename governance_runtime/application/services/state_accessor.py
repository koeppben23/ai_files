"""State accessor — canonical getters for session state fields.

Eliminates the copy-paste key-acrobacy pattern:
    state.get("Phase") or state.get("phase") or ""

Usage:
    from governance_runtime.application.services.state_accessor import get_phase, get_active_gate
    phase = get_phase(state)
"""

from __future__ import annotations

from typing import Mapping


def _state_text(state: Mapping, *keys: str) -> str:
    """Return first non-empty string value for any of the given keys."""
    for key in keys:
        val = state.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _state_bool(state: Mapping, *keys: str) -> bool | None:
    """Return first truthy bool value for any of the given keys, or None."""
    for key in keys:
        val = state.get(key)
        if isinstance(val, bool):
            return val
    return None


def _state_int(state: Mapping, *keys: str) -> int:
    """Return first truthy int value for any of the given keys, defaulting to 0."""
    for key in keys:
        val = state.get(key)
        if isinstance(val, int) and val >= 0:
            return val
    return 0


# ── Phase / Gate ──────────────────────────────────────────────────────────


def get_phase(state: Mapping) -> str:
    """Return the current phase (e.g. '4', '5-ArchitectureReview', '6-PostFlight')."""
    return _state_text(state, "Phase", "phase")


def get_active_gate(state: Mapping) -> str:
    """Return the active gate name."""
    return _state_text(state, "active_gate", "ActiveGate")


def get_status(state: Mapping) -> str:
    """Return the session status (e.g. 'OK', 'error', 'blocked')."""
    return _state_text(state, "status", "Status")


def get_next_gate_condition(state: Mapping) -> str:
    """Return the condition text describing what the next gate requires."""
    return _state_text(state, "next_gate_condition", "NextGateCondition")


def get_mode(state: Mapping) -> str:
    """Return the operating mode (e.g. 'IN_PROGRESS', 'CLOSED')."""
    return _state_text(state, "Mode", "mode")


# ── Phase-6 Review ────────────────────────────────────────────────────────


def get_review_iterations(state: Mapping) -> int:
    """Return the current Phase-6 review iteration count."""
    return _state_int(state, "phase6_review_iterations", "phase6ReviewIterations")


def get_max_review_iterations(state: Mapping) -> int:
    """Return the maximum Phase-6 review iterations."""
    return _state_int(state, "phase6_max_review_iterations", "phase6MaxReviewIterations", "phase6_max_iterations")


def get_min_review_iterations(state: Mapping) -> int:
    """Return the minimum Phase-6 review iterations required."""
    return _state_int(state, "phase6_min_self_review_iterations", "phase6_min_review_iterations")


def get_revision_delta(state: Mapping) -> str:
    """Return the revision delta indicator (e.g. 'changed', 'unchanged')."""
    return _state_text(state, "phase6_revision_delta", "phase6RevisionDelta")


# ── Booleans ──────────────────────────────────────────────────────────────


def is_review_complete(state: Mapping) -> bool:
    """Return True if Phase-6 internal review is complete."""
    review = state.get("ImplementationReview")
    if isinstance(review, Mapping):
        val = review.get("implementation_review_complete")
        if isinstance(val, bool):
            return val
    return _state_bool(state, "implementation_review_complete", "ImplementationReviewComplete") or False


def is_workflow_complete(state: Mapping) -> bool:
    """Return True if the workflow is marked complete (after /review-decision approve)."""
    return _state_bool(state, "workflow_complete", "WorkflowComplete") or False


def is_implementation_authorized(state: Mapping) -> bool:
    """Return True if /implement authorization is set."""
    return _state_bool(state, "ImplementationAuthorized") or False


def is_implementation_blocked(state: Mapping) -> bool:
    """Return True if implementation is blocked."""
    return _state_bool(state, "implementation_blocked", "ImplementationBlocked") or False


# ── Plan Record ───────────────────────────────────────────────────────────


def get_plan_versions(state: Mapping) -> int:
    """Return the number of plan record versions."""
    return _state_int(state, "plan_record_versions", "PlanRecordVersions")


# ── Rework Clarification ─────────────────────────────────────────────────


def get_rework_clarification_input(state: Mapping) -> str:
    """Return the rework clarification input text (for /ticket, /plan, /continue routing)."""
    return _state_text(state, "rework_clarification_input", "reworkClarificationInput")


# ── Phase-5 ───────────────────────────────────────────────────────────────


def is_phase5_completed(state: Mapping) -> bool:
    """Return True if Phase-5 is completed."""
    return _state_bool(state, "phase5_completed", "phase5Completed") or False
