"""Regulated Mode — Domain model for regulated customer operating mode.

Defines the regulated mode state machine and its effects on the governance
system. When regulated mode is active, additional constraints are enforced:

- Retention periods are locked (cannot be shortened)
- Purge operations require elevated authorization
- All access is audit-logged
- Redaction overrides require compliance officer role
- Export operations produce tamper-evident bundles

Contract version: REGULATED_MODE.v1

Design:
    - Frozen dataclasses for immutable state records
    - Pure functions for mode evaluation (no I/O)
    - Fail-closed: regulated mode defaults to active if state is ambiguous
    - Zero external dependencies (stdlib only)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "REGULATED_MODE.v1"


class RegulatedModeState(Enum):
    """Regulated mode lifecycle states."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    TRANSITIONING = "transitioning"


class RegulatedModeConstraint(Enum):
    """Constraints enforced when regulated mode is active."""
    RETENTION_LOCKED = "retention_locked"
    PURGE_REQUIRES_AUTHORIZATION = "purge_requires_authorization"
    ACCESS_AUDIT_LOGGED = "access_audit_logged"
    REDACTION_OVERRIDE_REQUIRES_CO = "redaction_override_requires_compliance_officer"
    EXPORT_TAMPER_EVIDENT = "export_tamper_evident"
    ARCHIVE_IMMUTABLE = "archive_immutable"
    CLASSIFICATION_ENFORCED = "classification_enforced"


# ---------------------------------------------------------------------------
# Mode configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegulatedModeConfig:
    """Configuration for regulated mode behavior."""
    state: RegulatedModeState
    customer_id: str = ""
    compliance_framework: str = ""
    activated_at: str = ""
    activated_by: str = ""
    minimum_retention_days: int = 365
    export_format: str = "zip"
    require_checksums_on_export: bool = True


@dataclass(frozen=True)
class RegulatedModeEvaluation:
    """Result of evaluating the regulated mode state."""
    is_active: bool
    state: RegulatedModeState
    active_constraints: tuple[RegulatedModeConstraint, ...]
    reason: str


#: Default config (regulated mode inactive)
DEFAULT_CONFIG = RegulatedModeConfig(state=RegulatedModeState.INACTIVE)

#: Constraints enforced when regulated mode is active
ACTIVE_CONSTRAINTS: tuple[RegulatedModeConstraint, ...] = (
    RegulatedModeConstraint.RETENTION_LOCKED,
    RegulatedModeConstraint.PURGE_REQUIRES_AUTHORIZATION,
    RegulatedModeConstraint.ACCESS_AUDIT_LOGGED,
    RegulatedModeConstraint.REDACTION_OVERRIDE_REQUIRES_CO,
    RegulatedModeConstraint.EXPORT_TAMPER_EVIDENT,
    RegulatedModeConstraint.ARCHIVE_IMMUTABLE,
    RegulatedModeConstraint.CLASSIFICATION_ENFORCED,
)

#: No constraints when inactive
INACTIVE_CONSTRAINTS: tuple[RegulatedModeConstraint, ...] = ()


# ---------------------------------------------------------------------------
# Compliance frameworks
# ---------------------------------------------------------------------------

#: Known compliance frameworks and their minimum retention requirements
COMPLIANCE_FRAMEWORKS: Mapping[str, int] = {
    "DATEV": 3650,       # 10 years
    "GoBD": 3650,        # 10 years (German tax law)
    "BaFin": 1825,       # 5 years (German banking regulation)
    "SOX": 2555,         # 7 years (US Sarbanes-Oxley)
    "GDPR": 365,         # 1 year default (varies by purpose)
    "Basel_III": 1825,   # 5 years (international banking)
    "ISO_27001": 1095,   # 3 years (information security)
    "DEFAULT": 365,      # 1 year fallback
}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def evaluate_mode(config: RegulatedModeConfig) -> RegulatedModeEvaluation:
    """Evaluate the current regulated mode state.

    Fail-closed: ambiguous states are treated as active.
    """
    if config.state == RegulatedModeState.ACTIVE:
        return RegulatedModeEvaluation(
            is_active=True,
            state=RegulatedModeState.ACTIVE,
            active_constraints=ACTIVE_CONSTRAINTS,
            reason="Regulated mode is active",
        )
    elif config.state == RegulatedModeState.TRANSITIONING:
        # Fail-closed: treat transitioning as active
        return RegulatedModeEvaluation(
            is_active=True,
            state=RegulatedModeState.TRANSITIONING,
            active_constraints=ACTIVE_CONSTRAINTS,
            reason="Regulated mode is transitioning — constraints enforced (fail-closed)",
        )
    else:
        return RegulatedModeEvaluation(
            is_active=False,
            state=RegulatedModeState.INACTIVE,
            active_constraints=INACTIVE_CONSTRAINTS,
            reason="Regulated mode is inactive",
        )


def get_minimum_retention_days(framework: str) -> int:
    """Get the minimum retention period for a compliance framework.

    Falls back to DEFAULT (365 days) for unknown frameworks.
    """
    return COMPLIANCE_FRAMEWORKS.get(framework, COMPLIANCE_FRAMEWORKS["DEFAULT"])


def is_constraint_active(
    config: RegulatedModeConfig,
    constraint: RegulatedModeConstraint,
) -> bool:
    """Check if a specific constraint is active under the current config."""
    evaluation = evaluate_mode(config)
    return constraint in evaluation.active_constraints


def validate_retention_change(
    *,
    config: RegulatedModeConfig,
    current_retention_days: int,
    requested_retention_days: int,
) -> tuple[bool, str]:
    """Validate whether a retention period change is allowed.

    In regulated mode, retention can only be extended, never shortened
    below the framework minimum.

    Returns:
        (allowed, reason) tuple
    """
    evaluation = evaluate_mode(config)

    if not evaluation.is_active:
        return True, "Retention change allowed (regulated mode inactive)"

    framework_min = get_minimum_retention_days(config.compliance_framework)
    effective_min = max(config.minimum_retention_days, framework_min)

    if requested_retention_days < effective_min:
        return False, (
            f"Cannot reduce retention below {effective_min} days "
            f"(framework={config.compliance_framework}, "
            f"minimum={effective_min})"
        )

    if requested_retention_days < current_retention_days:
        return False, (
            f"Cannot shorten retention from {current_retention_days} to "
            f"{requested_retention_days} days in regulated mode"
        )

    return True, "Retention change allowed"


def regulated_mode_summary(config: RegulatedModeConfig) -> dict[str, object]:
    """Return a machine-readable summary of the regulated mode state."""
    evaluation = evaluate_mode(config)
    return {
        "contract_version": CONTRACT_VERSION,
        "state": config.state.value,
        "is_active": evaluation.is_active,
        "customer_id": config.customer_id,
        "compliance_framework": config.compliance_framework,
        "minimum_retention_days": config.minimum_retention_days,
        "active_constraints": [c.value for c in evaluation.active_constraints],
        "reason": evaluation.reason,
    }


__all__ = [
    "CONTRACT_VERSION",
    "RegulatedModeState",
    "RegulatedModeConstraint",
    "RegulatedModeConfig",
    "RegulatedModeEvaluation",
    "DEFAULT_CONFIG",
    "ACTIVE_CONSTRAINTS",
    "INACTIVE_CONSTRAINTS",
    "COMPLIANCE_FRAMEWORKS",
    "evaluate_mode",
    "get_minimum_retention_days",
    "is_constraint_active",
    "validate_retention_change",
    "regulated_mode_summary",
]
