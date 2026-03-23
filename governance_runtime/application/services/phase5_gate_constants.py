"""Gate constants and configuration for Phase 5 governance.

Centralizes gate names, reason codes, terminal values, and phase mappings
to avoid scattered string literals and implicit state-machine duplicates.

Usage:
    from governance_runtime.application.services.phase5_gate_constants import (
        P5_GATE_PRIORITY_ORDER,
        P5_GATE_TERMINAL_VALUES,
        GATE_TO_PHASE_NEXT,
        reason_code_for_gate,
    )
"""

from __future__ import annotations

# ── Reason codes (blocking reasons when Phase 6 promotion is blocked) ────

_BLOCKED_P6_PREREQUISITES_NOT_MET = "BLOCKED-P6-PREREQUISITES-NOT-MET"
_BLOCKED_P5_3_TEST_QUALITY_GATE = "BLOCKED-P5-3-TEST-QUALITY-GATE"
_BLOCKED_P5_4_BUSINESS_RULES_GATE = "BLOCKED-P5-4-BUSINESS-RULES-GATE"
_BLOCKED_P5_5_TECHNICAL_DEBT_GATE = "BLOCKED-P5-5-TECHNICAL-DEBT-GATE"
_BLOCKED_P5_6_ROLLBACK_SAFETY_GATE = "BLOCKED-P5-6-ROLLBACK-SAFETY-GATE"

_GATE_TO_REASON_CODE: dict[str, str] = {
    "P5-Architecture": _BLOCKED_P6_PREREQUISITES_NOT_MET,
    "P5.3-TestQuality": _BLOCKED_P5_3_TEST_QUALITY_GATE,
    "P5.4-BusinessRules": _BLOCKED_P5_4_BUSINESS_RULES_GATE,
    "P5.5-TechnicalDebt": _BLOCKED_P5_5_TECHNICAL_DEBT_GATE,
    "P5.6-RollbackSafety": _BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
}


def reason_code_for_gate(gate_key: str) -> str:
    """Return the blocking reason code for a given gate key.

    Args:
        gate_key: Gate identifier (e.g., "P5-Architecture").

    Returns:
        Reason code string (e.g., "BLOCKED-P6-PREREQUISITES-NOT-MET").
    """
    return _GATE_TO_REASON_CODE.get(gate_key, _BLOCKED_P6_PREREQUISITES_NOT_MET)


# ── Gate priority order (SSOT for gate evaluation order) ─────────────────

P5_GATE_PRIORITY_ORDER: tuple[str, ...] = (
    "P5-Architecture",
    "P5.3-TestQuality",
    "P5.4-BusinessRules",
    "P5.5-TechnicalDebt",
    "P5.6-RollbackSafety",
)


# ── Terminal values (states that mean the gate is resolved) ──────────────

P5_GATE_TERMINAL_VALUES: dict[str, tuple[str, ...]] = {
    "P5-Architecture": ("approved",),
    "P5.3-TestQuality": ("pass", "pass-with-exceptions", "not-applicable"),
    "P5.4-BusinessRules": ("compliant", "compliant-with-exceptions", "not-applicable"),
    "P5.5-TechnicalDebt": ("approved", "not-applicable"),
    "P5.6-RollbackSafety": ("approved", "not-applicable"),
}


# ── Gate-to-phase mapping (for correcting Phase 6 / open-P5 inconsistencies) ──

GATE_TO_PHASE_NEXT: dict[str, tuple[str, str, str]] = {
    "P5.3-TestQuality": ("5.3-TestQuality", "5.3", "Test Quality Gate"),
    "P5.4-BusinessRules": ("5.4-BusinessRules", "5.4", "Business Rules Validation"),
    "P5.5-TechnicalDebt": ("5.5-TechnicalDebt", "5.5", "Technical Debt Review"),
    "P5.6-RollbackSafety": ("5.6-RollbackSafety", "5.6", "Rollback Safety Review"),
    "P5-Architecture": ("5-ArchitectureReview", "5", "Architecture Review Gate"),
}
