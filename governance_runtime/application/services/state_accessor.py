"""State accessor — canonical getters for session state fields.

Delegates alias resolution to the central StateNormalizer.

Usage:
    from governance_runtime.application.services.state_accessor import get_phase, get_active_gate
    phase = get_phase(state)
"""

from __future__ import annotations

from typing import Any, Mapping

from governance_runtime.application.services.state_normalizer import (
    normalize_to_canonical,
)


def _to_canonical(state: Mapping[str, Any]) -> dict[str, Any]:
    """Convert raw state to canonical form via StateNormalizer."""
    if isinstance(state, dict):
        return normalize_to_canonical(state)
    return normalize_to_canonical(dict(state))


def _get(state: Mapping, key: str) -> Any:
    """Get a field from canonical state."""
    canonical = _to_canonical(state)
    return canonical.get(key)


# ── Phase / Gate ──────────────────────────────────────────────────────────


def get_phase(state: Mapping) -> str:
    """Return the current phase (e.g. '4', '5-ArchitectureReview', '6-PostFlight')."""
    return str(_get(state, "phase") or "")


def get_next(state: Mapping) -> str:
    """Return the next phase token (e.g. '5', '6', '5.3')."""
    return str(_get(state, "next") or "")


def get_active_gate(state: Mapping) -> str:
    """Return the active gate name."""
    return str(_get(state, "active_gate") or "")


def get_status(state: Mapping) -> str:
    """Return the session status (e.g. 'OK', 'error', 'blocked')."""
    return str(_get(state, "status") or "")


def get_next_gate_condition(state: Mapping) -> str:
    """Return the condition text describing what the next gate requires."""
    return str(_get(state, "next_gate_condition") or "")


def get_mode(state: Mapping) -> str:
    """Return the operating mode (e.g. 'IN_PROGRESS', 'CLOSED')."""
    return str(_get(state, "mode") or "")


# ── Phase-6 Review ────────────────────────────────────────────────────────


def get_review_iterations(state: Mapping) -> int:
    """Return the current Phase-6 review iteration count."""
    val = _get(state, "phase6_review_iterations")
    if isinstance(val, int) and val >= 0:
        return val
    return 0


def get_max_review_iterations(state: Mapping) -> int:
    """Return the maximum Phase-6 review iterations."""
    val = _get(state, "phase6_max_review_iterations")
    if isinstance(val, int) and val >= 0:
        return val
    return 0


def get_min_review_iterations(state: Mapping) -> int:
    """Return the minimum Phase-6 review iterations required."""
    val = _get(state, "phase6_min_review_iterations")
    if isinstance(val, int) and val >= 0:
        return val
    return 0


def get_revision_delta(state: Mapping) -> str:
    """Return the revision delta indicator (e.g. 'changed', 'unchanged')."""
    return str(_get(state, "phase6_revision_delta") or "")


# ── Booleans ──────────────────────────────────────────────────────────────


def is_review_complete(state: Mapping) -> bool:
    """Return True if Phase-6 internal review is complete."""
    canonical = _to_canonical(state)
    review = canonical.get("implementation_review")
    if isinstance(review, Mapping):
        val = review.get("implementation_review_complete")
        if isinstance(val, bool):
            return val
    val = canonical.get("implementation_review_complete")
    if isinstance(val, bool):
        return val
    return False


def is_workflow_complete(state: Mapping) -> bool:
    """Return True if the workflow is marked complete (after /review-decision approve)."""
    val = _get(state, "workflow_complete")
    return isinstance(val, bool) and val


def is_implementation_authorized(state: Mapping) -> bool:
    """Return True if /implement authorization is set."""
    val = _get(state, "implementation_authorized")
    return isinstance(val, bool) and val


def is_implementation_blocked(state: Mapping) -> bool:
    """Return True if implementation is blocked."""
    val = _get(state, "implementation_blocked")
    return isinstance(val, bool) and val


# ── Plan Record ───────────────────────────────────────────────────────────


def get_plan_versions(state: Mapping) -> int:
    """Return the number of plan record versions."""
    val = _get(state, "plan_record_versions")
    if isinstance(val, int) and val >= 0:
        return val
    return 0


# ── Rework Clarification ─────────────────────────────────────────────────


def get_rework_clarification_input(state: Mapping) -> str:
    """Return the rework clarification input text (for /ticket, /plan, /continue routing)."""
    return str(_get(state, "rework_clarification_input") or "")


# ── Phase-5 ───────────────────────────────────────────────────────────────


def is_phase5_completed(state: Mapping) -> bool:
    """Return True if Phase-5 is completed."""
    val = _get(state, "phase5_completed")
    return isinstance(val, bool) and val
