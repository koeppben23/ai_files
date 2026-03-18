"""Retention Policy — Domain model for audit record lifecycle management.

Defines retention periods, legal holds, deletion rules, and archive targets
for regulated customer audit records. Retention rules operate on finalized
run archives and enforce minimum preservation periods per classification
level and compliance framework.

Contract version: RETENTION_POLICY.v1

Design:
    - Frozen dataclasses for immutable policy records
    - Pure functions for retention evaluation (no I/O)
    - Fail-closed: unknown classification → longest retention period
    - Zero external dependencies (stdlib only + governance.domain)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "RETENTION_POLICY.v1"


class RetentionClass(Enum):
    """Retention classification tiers aligned with data classification."""
    SHORT = "short"       # 1 year   — public/internal non-critical
    STANDARD = "standard" # 3 years  — internal operational
    EXTENDED = "extended"  # 7 years  — confidential (SOX, GoBD)
    PERMANENT = "permanent"  # 10+ years — restricted/regulated (DATEV)


class LegalHoldStatus(Enum):
    """Legal hold lifecycle states."""
    NONE = "none"
    ACTIVE = "active"
    RELEASED = "released"


class DeletionDecision(Enum):
    """Result of evaluating whether a record may be deleted."""
    ALLOWED = "allowed"
    BLOCKED_RETENTION = "blocked_retention"
    BLOCKED_LEGAL_HOLD = "blocked_legal_hold"
    BLOCKED_REGULATED_MODE = "blocked_regulated_mode"


class ArchiveFormat(Enum):
    """Supported archive export formats."""
    DIRECTORY = "directory"
    ZIP = "zip"


# ---------------------------------------------------------------------------
# Frozen domain models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetentionPeriod:
    """Retention period definition for a classification level."""
    classification_level: str
    retention_class: RetentionClass
    minimum_days: int
    description: str


@dataclass(frozen=True)
class LegalHold:
    """Legal hold record suspending deletion for a scope."""
    hold_id: str
    scope_type: str         # "run", "repo", "all"
    scope_value: str        # run_id, repo_fingerprint, or "*"
    reason: str
    status: LegalHoldStatus
    created_at: str         # RFC3339 UTC Z
    created_by: str
    released_at: str = ""   # RFC3339 UTC Z, empty if active
    released_by: str = ""


@dataclass(frozen=True)
class DeletionEvaluation:
    """Result of evaluating whether a record may be deleted."""
    decision: DeletionDecision
    reason: str
    blocking_hold_id: str = ""
    remaining_retention_days: int = 0


@dataclass(frozen=True)
class RetentionPolicy:
    """Complete retention policy configuration."""
    version: str
    contract_version: str
    default_retention_class: RetentionClass
    periods: tuple[RetentionPeriod, ...]
    legal_holds: tuple[LegalHold, ...]
    regulated_mode_minimum_days: int


@dataclass(frozen=True)
class ArchiveExportManifest:
    """Manifest for an exported archive bundle."""
    schema: str
    repo_fingerprint: str
    run_id: str
    exported_at: str
    exported_by: str
    export_format: str
    source_archive_path: str
    files_included: tuple[str, ...]
    checksums_verified: bool
    redaction_applied: bool
    redaction_max_level: str
    bundle_manifest_hash: str


@dataclass(frozen=True)
class RestoreValidation:
    """Result of validating a restored archive bundle."""
    is_valid: bool
    manifest_present: bool
    checksums_verified: bool
    files_complete: bool
    errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Retention period catalog — SSOT
# ---------------------------------------------------------------------------

#: Default retention periods per classification level
RETENTION_PERIODS: Mapping[str, RetentionPeriod] = {
    "public": RetentionPeriod(
        classification_level="public",
        retention_class=RetentionClass.SHORT,
        minimum_days=365,
        description="Public data — 1 year minimum retention",
    ),
    "internal": RetentionPeriod(
        classification_level="internal",
        retention_class=RetentionClass.STANDARD,
        minimum_days=1095,
        description="Internal data — 3 year minimum retention",
    ),
    "confidential": RetentionPeriod(
        classification_level="confidential",
        retention_class=RetentionClass.EXTENDED,
        minimum_days=2555,
        description="Confidential data — 7 year minimum retention",
    ),
    "restricted": RetentionPeriod(
        classification_level="restricted",
        retention_class=RetentionClass.PERMANENT,
        minimum_days=3650,
        description="Restricted data — 10 year minimum retention (DATEV/GoBD level)",
    ),
}

#: Compliance framework retention overrides
FRAMEWORK_RETENTION_OVERRIDES: Mapping[str, int] = {
    "DATEV": 3650,       # 10 years
    "GoBD": 3650,        # 10 years
    "BaFin": 1825,       # 5 years
    "SOX": 2555,         # 7 years
    "GDPR": 365,         # 1 year (minimum; varies by purpose)
    "Basel_III": 1825,   # 5 years
    "ISO_27001": 1095,   # 3 years
}

#: Default retention for unknown classification (fail-closed: longest)
DEFAULT_RETENTION_DAYS = 3650

#: Valid legal hold scope types
VALID_HOLD_SCOPES: FrozenSet[str] = frozenset({"run", "repo", "all"})


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def get_retention_period(classification_level: str) -> RetentionPeriod:
    """Get the retention period for a classification level.

    Falls back to restricted/permanent (fail-closed) for unknown levels.
    """
    return RETENTION_PERIODS.get(
        classification_level,
        RETENTION_PERIODS["restricted"],
    )


def get_effective_retention_days(
    classification_level: str,
    compliance_framework: str = "",
) -> int:
    """Calculate the effective retention period considering framework overrides.

    Returns the maximum of:
    - The classification-level retention period
    - The compliance framework override (if any)
    """
    base_days = get_retention_period(classification_level).minimum_days
    framework_days = FRAMEWORK_RETENTION_OVERRIDES.get(compliance_framework, 0)
    return max(base_days, framework_days)


def evaluate_deletion(
    *,
    run_id: str,
    repo_fingerprint: str,
    classification_level: str,
    archived_at_days_ago: int,
    compliance_framework: str = "",
    regulated_mode_active: bool = False,
    regulated_mode_minimum_days: int = 0,
    legal_holds: Sequence[LegalHold] = (),
) -> DeletionEvaluation:
    """Evaluate whether a run archive may be deleted.

    Checks in order:
    1. Active legal holds (block unconditionally)
    2. Regulated mode minimum (block if within minimum)
    3. Retention period (block if within retention)
    4. Allow deletion

    Fail-closed: if evaluation fails, deletion is blocked.
    """
    # Check legal holds
    for hold in legal_holds:
        if hold.status != LegalHoldStatus.ACTIVE:
            continue
        if _hold_applies(hold, run_id=run_id, repo_fingerprint=repo_fingerprint):
            return DeletionEvaluation(
                decision=DeletionDecision.BLOCKED_LEGAL_HOLD,
                reason=f"Active legal hold: {hold.hold_id} — {hold.reason}",
                blocking_hold_id=hold.hold_id,
            )

    # Check regulated mode
    if regulated_mode_active and regulated_mode_minimum_days > 0:
        if archived_at_days_ago < regulated_mode_minimum_days:
            remaining = regulated_mode_minimum_days - archived_at_days_ago
            return DeletionEvaluation(
                decision=DeletionDecision.BLOCKED_REGULATED_MODE,
                reason=(
                    f"Regulated mode requires {regulated_mode_minimum_days} days retention, "
                    f"{remaining} days remaining"
                ),
                remaining_retention_days=remaining,
            )

    # Check classification-level retention
    effective_days = get_effective_retention_days(classification_level, compliance_framework)
    if archived_at_days_ago < effective_days:
        remaining = effective_days - archived_at_days_ago
        return DeletionEvaluation(
            decision=DeletionDecision.BLOCKED_RETENTION,
            reason=(
                f"Retention period: {effective_days} days "
                f"(level={classification_level}, framework={compliance_framework or 'none'}), "
                f"{remaining} days remaining"
            ),
            remaining_retention_days=remaining,
        )

    return DeletionEvaluation(
        decision=DeletionDecision.ALLOWED,
        reason="Retention period expired, no holds active, deletion allowed",
    )


def _hold_applies(
    hold: LegalHold,
    *,
    run_id: str,
    repo_fingerprint: str,
) -> bool:
    """Check if a legal hold applies to a specific run."""
    if hold.scope_type == "all":
        return True
    if hold.scope_type == "repo" and hold.scope_value == repo_fingerprint:
        return True
    if hold.scope_type == "run" and hold.scope_value == run_id:
        return True
    return False


def validate_legal_hold(hold: LegalHold) -> list[str]:
    """Validate a legal hold record for consistency.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []

    if not hold.hold_id:
        errors.append("hold_id is required")
    if hold.scope_type not in VALID_HOLD_SCOPES:
        errors.append(f"scope_type '{hold.scope_type}' not in {sorted(VALID_HOLD_SCOPES)}")
    if not hold.scope_value:
        errors.append("scope_value is required")
    if not hold.reason:
        errors.append("reason is required")
    if hold.status not in (LegalHoldStatus.NONE, LegalHoldStatus.ACTIVE, LegalHoldStatus.RELEASED):
        errors.append(f"status '{hold.status}' is invalid")
    if not hold.created_at:
        errors.append("created_at is required")
    if not hold.created_by:
        errors.append("created_by is required")
    if hold.status == LegalHoldStatus.RELEASED:
        if not hold.released_at:
            errors.append("released_at is required when status is released")
        if not hold.released_by:
            errors.append("released_by is required when status is released")

    return errors


def validate_retention_policy(policy: RetentionPolicy) -> list[str]:
    """Validate a complete retention policy for consistency.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []

    if policy.contract_version != CONTRACT_VERSION:
        errors.append(
            f"contract_version mismatch: expected {CONTRACT_VERSION}, "
            f"got {policy.contract_version}"
        )
    if policy.regulated_mode_minimum_days < 0:
        errors.append("regulated_mode_minimum_days cannot be negative")

    seen_levels: set[str] = set()
    for period in policy.periods:
        if period.classification_level in seen_levels:
            errors.append(
                f"duplicate retention period for level: {period.classification_level}"
            )
        seen_levels.add(period.classification_level)
        if period.minimum_days < 0:
            errors.append(
                f"negative minimum_days for level {period.classification_level}"
            )

    for hold in policy.legal_holds:
        hold_errors = validate_legal_hold(hold)
        for err in hold_errors:
            errors.append(f"legal_hold[{hold.hold_id}]: {err}")

    return errors


def build_retention_policy(
    *,
    version: str = "1.0.0",
    regulated_mode_minimum_days: int = 3650,
    legal_holds: Sequence[LegalHold] = (),
) -> RetentionPolicy:
    """Build a default retention policy with the standard period catalog."""
    return RetentionPolicy(
        version=version,
        contract_version=CONTRACT_VERSION,
        default_retention_class=RetentionClass.STANDARD,
        periods=tuple(RETENTION_PERIODS.values()),
        legal_holds=tuple(legal_holds),
        regulated_mode_minimum_days=regulated_mode_minimum_days,
    )


def get_retention_summary(policy: RetentionPolicy) -> dict[str, object]:
    """Return a machine-readable summary of the retention policy."""
    return {
        "contract_version": policy.contract_version,
        "version": policy.version,
        "default_retention_class": policy.default_retention_class.value,
        "regulated_mode_minimum_days": policy.regulated_mode_minimum_days,
        "periods": [
            {
                "classification_level": p.classification_level,
                "retention_class": p.retention_class.value,
                "minimum_days": p.minimum_days,
                "description": p.description,
            }
            for p in policy.periods
        ],
        "active_legal_holds": sum(
            1 for h in policy.legal_holds
            if h.status == LegalHoldStatus.ACTIVE
        ),
        "total_legal_holds": len(policy.legal_holds),
        "framework_overrides": dict(FRAMEWORK_RETENTION_OVERRIDES),
    }


__all__ = [
    "CONTRACT_VERSION",
    "RetentionClass",
    "LegalHoldStatus",
    "DeletionDecision",
    "ArchiveFormat",
    "RetentionPeriod",
    "LegalHold",
    "DeletionEvaluation",
    "RetentionPolicy",
    "ArchiveExportManifest",
    "RestoreValidation",
    "RETENTION_PERIODS",
    "FRAMEWORK_RETENTION_OVERRIDES",
    "DEFAULT_RETENTION_DAYS",
    "VALID_HOLD_SCOPES",
    "get_retention_period",
    "get_effective_retention_days",
    "evaluate_deletion",
    "validate_legal_hold",
    "validate_retention_policy",
    "build_retention_policy",
    "get_retention_summary",
]
