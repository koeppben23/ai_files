"""State normalizer - resolves legacy field names to canonical names.

ARCHITECTURE RULE: This is the ONLY module allowed to resolve field aliases.
Kernel code MUST use CanonicalSessionState via normalize_to_canonical().

Usage:
    from governance_runtime.application.services.state_normalizer import normalize_to_canonical

    canonical = normalize_to_canonical(raw_state)
    phase = canonical["phase"]  # guaranteed canonical name

For conflict detection (used by critical boundary paths):
    from governance_runtime.application.services.state_normalizer import normalize_with_conflicts

    result = normalize_with_conflicts(raw_state)
    if result.conflicts:
        raise InvalidStateError(f"Conflicts detected: {result.conflicts}")
    canonical = result.canonical
"""

from __future__ import annotations

from typing import Any

from governance_runtime.application.dto.canonical_state import (
    CanonicalGates,
    CanonicalImplementationPackage,
    CanonicalImplementationReview,
    CanonicalKernel,
    CanonicalLoadedRulebooks,
    CanonicalP54BusinessRules,
    CanonicalReviewPackage,
    CanonicalSessionState,
    ConflictDetail,
    NormalizationResult,
)
from governance_runtime.application.dto.field_aliases import (
    FIELD_ALIASES,
    GATE_KEY_ALIASES,
    IMPLEMENTATION_PACKAGE_ALIASES,
    IMPLEMENTATION_REVIEW_ALIASES,
    KERNEL_ALIASES,
    LOADED_RULEBOOKS_ALIASES,
    P54_ALIASES,
    REVIEW_PACKAGE_ALIASES,
)


def normalize_to_canonical(state: dict[str, Any]) -> CanonicalSessionState:
    """Convert legacy state dict to canonical CanonicalSessionState.

    This is the PRIMARY entry point for kernel code to access state.
    Returns a NEW dict - never mutates the input.

    Args:
        state: Raw state dict (may contain legacy field names).

    Returns:
        CanonicalSessionState with only canonical field names.
    """
    result: CanonicalSessionState = {}

    # Top-level fields
    for canonical, aliases in FIELD_ALIASES.items():
        value = _resolve_field(state, canonical, aliases)
        if value is not None:
            result[canonical] = value

    # Nested: Gates
    raw_gates = state.get("Gates") or state.get("gates")
    if isinstance(raw_gates, dict):
        result["gates"] = _normalize_gates(raw_gates)

    # Nested: ImplementationReview
    raw_review = state.get("ImplementationReview")
    if isinstance(raw_review, dict):
        result["implementation_review"] = _normalize_implementation_review(raw_review)

    # Nested: P5.4 Business Rules (flatten from top-level p54_* fields)
    p54 = _normalize_p54(state)
    if p54:
        result["p54"] = p54

    # Nested: Review Package (flatten from review_package_* fields)
    result["review_package"] = _normalize_review_package(state)

    # Nested: Implementation Package (flatten from implementation_package_* fields)
    result["implementation_package"] = _normalize_implementation_package(state)

    # Nested: Kernel
    raw_kernel = state.get("Kernel") or state.get("kernel")
    if isinstance(raw_kernel, dict):
        result["kernel"] = _normalize_kernel(raw_kernel)

    # Nested: LoadedRulebooks
    raw_rulebooks = state.get("LoadedRulebooks") or state.get("loaded_rulebooks")
    if isinstance(raw_rulebooks, dict):
        result["loaded_rulebooks"] = _normalize_loaded_rulebooks(raw_rulebooks)

    return result


def _resolve_field(
    source: dict[str, Any],
    canonical: str,
    aliases: list[str],
) -> Any:
    """Resolve a field from source, trying canonical first, then aliases."""
    # Try canonical name first
    if canonical in source and source[canonical] is not None:
        return source[canonical]

    # Try aliases
    for alias in aliases:
        if alias in source and source[alias] is not None:
            return source[alias]

    return None


def _normalize_gates(raw: dict[str, Any]) -> CanonicalGates:
    """Convert Gates dict with legacy keys to canonical keys."""
    result: CanonicalGates = {}
    for legacy_key, value in raw.items():
        canonical_key = GATE_KEY_ALIASES.get(legacy_key)
        if canonical_key and value is not None:
            result[canonical_key] = str(value)
    return result


def _normalize_implementation_review(raw: dict[str, Any]) -> CanonicalImplementationReview:
    """Convert ImplementationReview block to canonical form."""
    result: CanonicalImplementationReview = {}
    for canonical, aliases in IMPLEMENTATION_REVIEW_ALIASES.items():
        value = _resolve_field(raw, canonical, aliases)
        if value is not None:
            result[canonical] = value
    return result


def _normalize_p54(state: dict[str, Any]) -> CanonicalP54BusinessRules:
    """Extract P5.4 fields from state into nested block."""
    result: CanonicalP54BusinessRules = {}
    for canonical in P54_ALIASES.keys():
        # P5.4 fields are at top level with p54_ prefix
        value = state.get(f"p54_{canonical}")
        if value is not None:
            result[canonical] = value
    return result


def _normalize_review_package(state: dict[str, Any]) -> CanonicalReviewPackage:
    """Extract review package fields from state into nested block.

    Reads from:
    1. Existing nested 'ReviewPackage' key (preferred)
    2. Flat review_package_* fields via aliases (legacy fallback)

    When nested ReviewPackage exists but is incomplete, missing fields are
    filled from flat review_package_* fields to prevent silent data loss.

    Args:
        state: Raw state dict.

    Returns:
        CanonicalReviewPackage with normalized fields.
    """
    result: CanonicalReviewPackage = {}

    existing = state.get("ReviewPackage")
    if isinstance(existing, dict) and existing:
        result = _normalize_review_package_from_dict(existing)

    for canonical, aliases in REVIEW_PACKAGE_ALIASES.items():
        if canonical in result:
            continue
        value = _resolve_field(state, canonical, aliases)
        if value is not None:
            result[canonical] = value

    return result


def _normalize_review_package_from_dict(source: dict[str, Any]) -> CanonicalReviewPackage:
    """Normalize a ReviewPackage dict to canonical form.

    Args:
        source: Dict that may contain canonical or alias field names.

    Returns:
        CanonicalReviewPackage with normalized fields.
    """
    result: CanonicalReviewPackage = {}
    for canonical, aliases in REVIEW_PACKAGE_ALIASES.items():
        value = _resolve_field(source, canonical, aliases)
        if value is not None:
            result[canonical] = value
    return result


def _normalize_implementation_package(state: dict[str, Any]) -> CanonicalImplementationPackage:
    """Extract implementation package fields from state into nested block."""
    result: CanonicalImplementationPackage = {}
    for canonical, aliases in IMPLEMENTATION_PACKAGE_ALIASES.items():
        value = _resolve_field(state, canonical, aliases)
        if value is not None:
            result[canonical] = value
    return result


def _normalize_kernel(raw: dict[str, Any]) -> CanonicalKernel:
    """Convert Kernel block to canonical form."""
    result: CanonicalKernel = {}
    for canonical, aliases in KERNEL_ALIASES.items():
        value = _resolve_field(raw, canonical, aliases)
        if value is not None:
            result[canonical] = value
    return result


def _normalize_loaded_rulebooks(raw: dict[str, Any]) -> CanonicalLoadedRulebooks:
    """Convert LoadedRulebooks block to canonical form."""
    result: CanonicalLoadedRulebooks = {}
    for canonical, aliases in LOADED_RULEBOOKS_ALIASES.items():
        value = _resolve_field(raw, canonical, aliases)
        if value is not None:
            result[canonical] = value
    return result


def get_gate(canonical_gates: CanonicalGates, gate_name: str) -> str | None:
    """Get a gate status by canonical or legacy name.

    Args:
        canonical_gates: The gates dict from canonical state.
        gate_name: Canonical name (P5_3_TestQuality) or legacy (P5.3-TestQuality).

    Returns:
        Gate status string or None if not found.
    """
    # Try canonical name first
    if gate_name in canonical_gates:
        return canonical_gates[gate_name]

    # Try legacy name
    canonical_key = GATE_KEY_ALIASES.get(gate_name)
    if canonical_key and canonical_key in canonical_gates:
        return canonical_gates[canonical_key]

    return None


def get_all_gate_statuses(canonical_gates: CanonicalGates) -> dict[str, str]:
    """Get all gate statuses with canonical keys.

    Returns:
        Dict mapping canonical gate names to their status.
    """
    return dict(canonical_gates)


def is_gate_passed(canonical_gates: CanonicalGates, gate_name: str) -> bool:
    """Check if a gate is in a passed terminal state.

    Args:
        canonical_gates: The gates dict from canonical state.
        gate_name: Canonical or legacy gate name.

    Returns:
        True if gate status indicates passed/approved.
    """
    status = get_gate(canonical_gates, gate_name)
    if status is None:
        return False

    terminal_passed = {
        "approved", "pass", "compliant", "compliant-with-exceptions",
        "pass-with-exceptions", "not-applicable",
    }
    return status.lower() in terminal_passed


def is_gate_pending(canonical_gates: CanonicalGates, gate_name: str) -> bool:
    """Check if a gate is pending.

    Args:
        canonical_gates: The gates dict from canonical state.
        gate_name: Canonical or legacy gate name.

    Returns:
        True if gate status is pending.
    """
    status = get_gate(canonical_gates, gate_name)
    return status is not None and status.lower() == "pending"


def normalize_with_conflicts(state: dict[str, Any]) -> NormalizationResult:
    """Normalize state with conflict detection for critical boundary paths.

    This function extends normalize_to_canonical with conflict detection.
    Use this at critical boundaries where fail-closed behavior is required.

    Conflict Policy:
        - No conflict: normalize normally
        - Both representations consistent: ReviewPackage wins, log warning
        - Both representations conflicting: fail-closed, add to conflicts list

    Args:
        state: Raw state dict (may contain legacy field names).

    Returns:
        NormalizationResult with canonical state and any detected conflicts.
    """
    conflicts: list[ConflictDetail] = []
    warnings: list[str] = []

    canonical = normalize_to_canonical(state)

    flat_conflicts, flat_warnings = _detect_review_package_conflicts(state, canonical)
    conflicts.extend(flat_conflicts)
    warnings.extend(flat_warnings)

    return NormalizationResult(
        canonical=canonical,
        conflicts=conflicts,
        warnings=warnings,
    )


def _detect_review_package_conflicts(
    raw: dict[str, Any],
    canonical: CanonicalSessionState,
) -> tuple[list[ConflictDetail], list[str]]:
    """Detect conflicts between flat review_package_* fields and nested ReviewPackage.

    Conflict Policy:
        - Only flat fields: normalizes correctly, no conflict
        - Only nested ReviewPackage: normalizes correctly, no conflict
        - Both present and consistent: ReviewPackage wins, warning logged
        - Both present and conflicting: fail-closed, conflict reported

    Args:
        raw: Raw input state with potentially flat fields.
        canonical: Already-normalized state with nested ReviewPackage.

    Returns:
        Tuple of (conflicts, warnings). Conflicts are semantic contradictions,
        warnings are non-critical duplicates.
    """
    conflicts: list[ConflictDetail] = []
    warnings: list[str] = []

    review_package = canonical.get("review_package", {})
    if not review_package:
        return conflicts, warnings

    nested_keys = set(review_package.keys())

    for canonical_field in nested_keys:
        aliases = REVIEW_PACKAGE_ALIASES.get(canonical_field, [])
        flat_value = None
        flat_source = None

        for alias in aliases:
            if alias in raw:
                flat_value = raw[alias]
                flat_source = alias
                break

        nested_value = review_package[canonical_field]

        if flat_value is None:
            continue

        if flat_value != nested_value:
            conflicts.append(ConflictDetail(
                field=canonical_field,
                flat_value=flat_value,
                nested_value=nested_value,
            ))
        else:
            warnings.append(f"Duplicate field: {flat_source} mirrors {canonical_field}")

    return conflicts, warnings


def has_review_package_conflicts(state: dict[str, Any]) -> bool:
    """Check if state has conflicting ReviewPackage representations.

    Convenience function for quick conflict checking.

    Args:
        state: Raw state dict to check.

    Returns:
        True if conflicts exist, False otherwise.
    """
    result = normalize_with_conflicts(state)
    return len(result["conflicts"]) > 0
