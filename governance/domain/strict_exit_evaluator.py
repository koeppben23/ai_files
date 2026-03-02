"""Strict-exit evaluator for principal_strict enforcement mode.

Implements the blocking-grade decision matrix:

                    │ missing       │ stale          │ below_threshold │
────────────────────┼───────────────┼────────────────┼─────────────────┤
critical: true      │ BLOCKED       │ BLOCKED        │ BLOCKED         │
critical: false     │ NOT_VERIFIED  │ NOT_VERIFIED   │ WARN            │

Only active when ``PolicyMode.principal_strict`` is ``True``.  When
principal_strict is ``False``, all verdicts downgrade to ``"warn"``.

The evaluator is **pure domain logic** — no I/O, no state mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal, Mapping, Sequence

from governance.domain.evidence_policy import (
    EVIDENCE_CLASS_DEFAULT_TTL_SECONDS,
    is_stale,
    parse_observed_at,
    resolve_freshness_class,
    resolve_ttl_seconds,
)
from governance.domain.reason_codes import (
    BLOCKED_STRICT_EVIDENCE_MISSING,
    BLOCKED_STRICT_EVIDENCE_STALE,
    BLOCKED_STRICT_THRESHOLD,
    NOT_VERIFIED_STRICT_EVIDENCE_MISSING,
    NOT_VERIFIED_STRICT_EVIDENCE_STALE,
    REASON_CODE_NONE,
)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

StrictVerdict = Literal["blocked", "not_verified", "warn", "ok"]


@dataclass(frozen=True)
class CriterionResult:
    """Evaluation result for a single ``pass_criteria`` entry."""

    criterion_key: str
    artifact_kind: str
    critical: bool
    verdict: StrictVerdict
    reason_code: str
    detail: str


@dataclass(frozen=True)
class StrictExitResult:
    """Aggregate result for the strict-exit gate across all criteria."""

    blocked: bool
    criteria: tuple[CriterionResult, ...]
    reason_codes: tuple[str, ...]
    summary: str


# ---------------------------------------------------------------------------
# Threshold resolution
# ---------------------------------------------------------------------------

# Built-in resolver names → callables.
# Each resolver takes (artifact_kind, evidence_value, risk_tier) and returns
# (passed: bool, detail: str).

_ThresholdResolver = Any  # callable[[str, object, str], tuple[bool, str]]


def _resolve_dynamic_by_risk_tier(
    artifact_kind: str,
    evidence_value: object,
    risk_tier: str,
) -> tuple[bool, str]:
    """Dynamic threshold resolver that adjusts by risk tier.

    Default thresholds (lowered for lower tiers):
        critical / high → 80%
        medium          → 60%
        low / unknown   → 40%
    """
    tier = risk_tier.strip().lower() if isinstance(risk_tier, str) else "unknown"
    thresholds: dict[str, float] = {
        "critical": 80.0,
        "high": 80.0,
        "medium": 60.0,
        "low": 40.0,
    }
    required = thresholds.get(tier, 40.0)

    if isinstance(evidence_value, (int, float)):
        numeric = float(evidence_value)
    elif isinstance(evidence_value, str):
        try:
            numeric = float(evidence_value.strip().rstrip("%"))
        except ValueError:
            return False, f"non-numeric evidence value: {evidence_value!r}"
    else:
        return False, f"unsupported evidence type: {type(evidence_value).__name__}"

    if numeric >= required:
        return True, f"{numeric:.1f}% >= {required:.1f}% (tier={tier})"
    return False, f"{numeric:.1f}% < {required:.1f}% (tier={tier})"


_BUILTIN_RESOLVERS: Final[dict[str, _ThresholdResolver]] = {
    "dynamic_by_risk_tier": _resolve_dynamic_by_risk_tier,
}


def get_threshold_resolver(name: str) -> _ThresholdResolver | None:
    """Look up a built-in threshold resolver by name."""
    return _BUILTIN_RESOLVERS.get(name.strip().lower())


# ---------------------------------------------------------------------------
# Per-criterion evaluation
# ---------------------------------------------------------------------------

def _evaluate_criterion(
    *,
    criterion: Mapping[str, object],
    evidence_map: Mapping[str, Mapping[str, object]],
    risk_tier: str,
    now_utc: datetime,
    principal_strict: bool,
) -> CriterionResult:
    """Evaluate one ``pass_criteria`` entry against available evidence."""

    artifact_kind = str(criterion.get("artifact_kind", "")).strip()
    critical = criterion.get("critical") is True
    criterion_key = str(criterion.get("criterion_key", artifact_kind)).strip()

    # 1. Check evidence presence
    evidence = evidence_map.get(artifact_kind)
    if evidence is None:
        if not principal_strict:
            return CriterionResult(
                criterion_key=criterion_key,
                artifact_kind=artifact_kind,
                critical=critical,
                verdict="warn",
                reason_code=REASON_CODE_NONE,
                detail="evidence missing (non-strict)",
            )
        if critical:
            return CriterionResult(
                criterion_key=criterion_key,
                artifact_kind=artifact_kind,
                critical=critical,
                verdict="blocked",
                reason_code=BLOCKED_STRICT_EVIDENCE_MISSING,
                detail="critical evidence missing",
            )
        return CriterionResult(
            criterion_key=criterion_key,
            artifact_kind=artifact_kind,
            critical=critical,
            verdict="not_verified",
            reason_code=NOT_VERIFIED_STRICT_EVIDENCE_MISSING,
            detail="non-critical evidence missing",
        )

    # 2. Check staleness
    freshness_class = resolve_freshness_class(artifact_kind)
    ttl = EVIDENCE_CLASS_DEFAULT_TTL_SECONDS.get(freshness_class, 24 * 60 * 60)
    observed_at = parse_observed_at(evidence.get("observed_at"))
    if is_stale(observed_at=observed_at, ttl_seconds=ttl, now_utc=now_utc):
        if not principal_strict:
            return CriterionResult(
                criterion_key=criterion_key,
                artifact_kind=artifact_kind,
                critical=critical,
                verdict="warn",
                reason_code=REASON_CODE_NONE,
                detail="evidence stale (non-strict)",
            )
        if critical:
            return CriterionResult(
                criterion_key=criterion_key,
                artifact_kind=artifact_kind,
                critical=critical,
                verdict="blocked",
                reason_code=BLOCKED_STRICT_EVIDENCE_STALE,
                detail="critical evidence stale",
            )
        return CriterionResult(
            criterion_key=criterion_key,
            artifact_kind=artifact_kind,
            critical=critical,
            verdict="not_verified",
            reason_code=NOT_VERIFIED_STRICT_EVIDENCE_STALE,
            detail="non-critical evidence stale",
        )

    # 3. Check threshold (only if criterion declares threshold_mode)
    threshold_mode = criterion.get("threshold_mode")
    if isinstance(threshold_mode, str) and threshold_mode.strip():
        resolver_name = str(criterion.get("threshold_resolver", threshold_mode)).strip()
        resolver = get_threshold_resolver(resolver_name)
        if resolver is None:
            # Unknown resolver → fail-closed in strict, warn otherwise
            if not principal_strict:
                return CriterionResult(
                    criterion_key=criterion_key,
                    artifact_kind=artifact_kind,
                    critical=critical,
                    verdict="warn",
                    reason_code=REASON_CODE_NONE,
                    detail=f"unknown threshold_resolver: {resolver_name} (non-strict)",
                )
            if critical:
                return CriterionResult(
                    criterion_key=criterion_key,
                    artifact_kind=artifact_kind,
                    critical=critical,
                    verdict="blocked",
                    reason_code=BLOCKED_STRICT_THRESHOLD,
                    detail=f"unknown threshold_resolver: {resolver_name}",
                )
            return CriterionResult(
                criterion_key=criterion_key,
                artifact_kind=artifact_kind,
                critical=critical,
                verdict="warn",
                reason_code=REASON_CODE_NONE,
                detail=f"unknown threshold_resolver: {resolver_name} (non-critical)",
            )

        evidence_value = evidence.get("value")
        passed, detail = resolver(artifact_kind, evidence_value, risk_tier)
        if not passed:
            if not principal_strict:
                return CriterionResult(
                    criterion_key=criterion_key,
                    artifact_kind=artifact_kind,
                    critical=critical,
                    verdict="warn",
                    reason_code=REASON_CODE_NONE,
                    detail=f"below threshold (non-strict): {detail}",
                )
            if critical:
                return CriterionResult(
                    criterion_key=criterion_key,
                    artifact_kind=artifact_kind,
                    critical=critical,
                    verdict="blocked",
                    reason_code=BLOCKED_STRICT_THRESHOLD,
                    detail=f"below threshold: {detail}",
                )
            return CriterionResult(
                criterion_key=criterion_key,
                artifact_kind=artifact_kind,
                critical=critical,
                verdict="warn",
                reason_code=REASON_CODE_NONE,
                detail=f"below threshold (non-critical): {detail}",
            )

    # 4. All checks passed
    return CriterionResult(
        criterion_key=criterion_key,
        artifact_kind=artifact_kind,
        critical=critical,
        verdict="ok",
        reason_code=REASON_CODE_NONE,
        detail="all checks passed",
    )


# ---------------------------------------------------------------------------
# Aggregate evaluator
# ---------------------------------------------------------------------------

def evaluate_strict_exit(
    *,
    pass_criteria: Sequence[Mapping[str, object]],
    evidence_map: Mapping[str, Mapping[str, object]],
    risk_tier: str = "unknown",
    now_utc: datetime,
    principal_strict: bool,
) -> StrictExitResult:
    """Evaluate all ``pass_criteria`` and return an aggregate strict-exit result.

    Args:
        pass_criteria: List of criterion dicts from the rulebook's
            ``phase_exit_contract[].pass_criteria``.
        evidence_map: Keyed by ``artifact_kind`` → dict with at least
            ``observed_at`` (ISO-8601) and optionally ``value``.
        risk_tier: Current risk tier (e.g. ``"high"``, ``"medium"``).
        now_utc: Current time in UTC (caller must provide; no side-effects
            in domain layer).
        principal_strict: Whether principal_strict enforcement is active.

    Returns:
        StrictExitResult with aggregate blocking status.
    """

    results: list[CriterionResult] = []
    for criterion in pass_criteria:
        results.append(
            _evaluate_criterion(
                criterion=criterion,
                evidence_map=evidence_map,
                risk_tier=risk_tier,
                now_utc=now_utc,
                principal_strict=principal_strict,
            )
        )

    blocked = any(r.verdict == "blocked" for r in results)
    reason_codes = tuple(
        r.reason_code for r in results if r.reason_code != REASON_CODE_NONE
    )

    if blocked:
        blocked_criteria = [r for r in results if r.verdict == "blocked"]
        summary = (
            f"strict-exit BLOCKED: {len(blocked_criteria)} critical "
            f"criterion/criteria failed"
        )
    elif any(r.verdict == "not_verified" for r in results):
        nv_criteria = [r for r in results if r.verdict == "not_verified"]
        summary = (
            f"strict-exit NOT_VERIFIED: {len(nv_criteria)} non-critical "
            f"criterion/criteria unverified"
        )
    elif any(r.verdict == "warn" for r in results):
        warn_criteria = [r for r in results if r.verdict == "warn"]
        summary = f"strict-exit WARN: {len(warn_criteria)} criterion/criteria warned"
    else:
        summary = "strict-exit OK: all criteria satisfied"

    return StrictExitResult(
        blocked=blocked,
        criteria=tuple(results),
        reason_codes=reason_codes,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# principal_strict derivation (fail-closed)
# ---------------------------------------------------------------------------

def resolve_principal_strict(
    *,
    profile_strict: bool | None = None,
    override_strict: bool | None = None,
    policy_strict: bool | None = None,
) -> bool:
    """Derive the effective ``principal_strict`` flag.

    Resolution order (highest precedence first):
        1. ``policy_strict``  — tenant-level policy override
        2. ``override_strict`` — session/operator override
        3. ``profile_strict``  — profile-level default

    **Fail-closed**: If *any* source declares strict=True, the result is True.
    This is intentionally NOT coupled to addon load status — if strict is
    requested but required addons are missing, the gate will BLOCK
    (not silently downgrade).
    """
    sources = [s for s in (policy_strict, override_strict, profile_strict) if s is not None]
    if not sources:
        return False
    # Fail-closed: any True → True
    return any(sources)
