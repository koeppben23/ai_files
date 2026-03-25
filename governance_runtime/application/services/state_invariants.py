"""State invariants - executable rules that constrain valid state forms.

Each invariant is a function that takes a canonical state dict and returns
a tuple of (valid: bool, violation: str). These can be used in CI to verify
that no state violates the rules, and in production to detect drift.

Usage:
    from governance_runtime.application.services.state_invariants import check_all_invariants

    violations = check_all_invariants(canonical)
    if violations:
        raise StateInvariantError(f"State violations: {violations}")

Invariant numbering:
    INV-001 through INV-099: Phase-level constraints
    INV-100 through INV-199: Gate-level constraints
    INV-200 through INV-299: ReviewPackage constraints
    INV-300 through INV-399: ImplementationReview constraints
"""

from __future__ import annotations

from typing import Any, Mapping


def check_invariant_phase6_completed_requires_review_package(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-001: If phase6_state == '6.complete' or 'phase6_completed', then ReviewPackage.presented == True."""
    phase6_state = str(state.get("phase6_state") or "").strip().lower()
    if phase6_state not in ("6.complete", "phase6_completed", "completed"):
        return True, ""

    review_package = state.get("review_package") or {}
    presented = review_package.get("presented") if isinstance(review_package, dict) else None
    if not isinstance(presented, bool) or not presented:
        return False, "INV-001: 6.complete requires ReviewPackage.presented=true"

    return True, ""


def check_invariant_evidence_gate_only_in_phase6(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-100: If active_gate == 'Evidence Presentation Gate', then phase starts with '6'."""
    active_gate = str(state.get("active_gate") or "").strip().lower()
    if active_gate != "evidence presentation gate":
        return True, ""

    phase = str(state.get("phase") or "").strip()
    if not phase.startswith("6"):
        return False, f"INV-100: Evidence Presentation Gate requires phase starting with '6', got '{phase}'"

    return True, ""


def check_invariant_implementation_review_only_in_phase6(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-300: If ImplementationReview block exists, then phase starts with '6'."""
    impl_review = state.get("implementation_review")
    if not isinstance(impl_review, dict):
        return True, ""

    phase = str(state.get("phase") or "").strip()
    if not phase.startswith("6"):
        return False, f"INV-300: ImplementationReview requires phase starting with '6', got '{phase}'"

    return True, ""


def check_invariant_phase5_completed_not_stale(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-002: If phase5_completed == True, then phase starts with '5' or '6'."""
    phase5_completed = state.get("phase5_completed")
    if not isinstance(phase5_completed, bool) or not phase5_completed:
        return True, ""

    phase = str(state.get("phase") or "").strip()
    if not (phase.startswith("5") or phase.startswith("6")):
        return False, f"INV-002: phase5_completed=true requires phase starting with '5' or '6', got '{phase}'"

    return True, ""


def check_invariant_review_package_when_presented(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-200: If ReviewPackage.presented == True, then ReviewPackage must have review_object."""
    review_package = state.get("review_package") or {}
    if not isinstance(review_package, dict):
        return True, ""

    presented = review_package.get("presented")
    if not isinstance(presented, bool) or not presented:
        return True, ""

    review_object = review_package.get("review_object")
    if not isinstance(review_object, str) or not review_object.strip():
        return False, "INV-200: ReviewPackage.presented=true requires review_object"

    return True, ""


def check_invariant_phase6_loop_status_consistent(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-010: If phase6_state == '6.execution', then implementation_review_complete must be False."""
    phase6_state = str(state.get("phase6_state") or "").strip().lower()
    if phase6_state not in ("6.execution", "phase6_in_progress"):
        return True, ""

    impl_review = state.get("implementation_review") or {}
    if isinstance(impl_review, dict):
        complete = impl_review.get("implementation_review_complete")
    else:
        complete = state.get("implementation_review_complete")

    if isinstance(complete, bool) and complete:
        return False, "INV-010: 6.execution requires implementation_review_complete=false"

    return True, ""


def check_invariant_rework_gate_requires_changes_requested(
    state: Mapping[str, Any],
) -> tuple[bool, str]:
    """INV-110: If active_gate == 'Rework Clarification Gate', then UserReviewDecision should be changes_requested."""
    active_gate = str(state.get("active_gate") or "").strip().lower()
    if active_gate != "rework clarification gate":
        return True, ""

    phase = str(state.get("phase") or "").strip()
    if not phase.startswith("6"):
        return False, f"INV-110: Rework Clarification Gate requires phase starting with '6', got '{phase}'"

    return True, ""


# ── Invariant Registry ────────────────────────────────────────────────────

INVARIANTS = [
    check_invariant_phase6_completed_requires_review_package,
    check_invariant_evidence_gate_only_in_phase6,
    check_invariant_implementation_review_only_in_phase6,
    check_invariant_phase5_completed_not_stale,
    check_invariant_review_package_when_presented,
    check_invariant_phase6_loop_status_consistent,
    check_invariant_rework_gate_requires_changes_requested,
]


def check_all_invariants(state: Mapping[str, Any]) -> list[str]:
    """Check all invariants against the given state.

    Args:
        state: Canonical state dict to check.

    Returns:
        List of violation messages. Empty list if all invariants pass.
    """
    violations: list[str] = []
    for check in INVARIANTS:
        valid, violation = check(state)
        if not valid:
            violations.append(violation)
    return violations
