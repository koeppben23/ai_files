"""Pure gate evaluation logic for Phase 5 gates.

These functions are pure: they take state and return status objects.
No state mutation, no IO, no boundary logic.

Usage:
    from governance_runtime.application.services.phase5_gate_evaluators import (
        evaluate_p53_test_quality,
        evaluate_p54_business_rules,
        evaluate_p55_technical_debt,
        evaluate_p56_rollback_safety,
        phase_1_5_executed,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GateEvaluationResult:
    """Result of a gate evaluation."""

    status: str


def phase_1_5_executed(state: Mapping[str, Any]) -> bool:
    """Check if Phase 1.5 (Business Rules) has been executed.

    Args:
        state: Session state.

    Returns:
        True if BusinessRules.Outcome == 'extracted' and ExecutionEvidence is set.
    """
    br = state.get("BusinessRules") or {}
    if not isinstance(br, Mapping):
        return False
    return bool(br.get("Outcome") == "extracted" and br.get("ExecutionEvidence"))


def evaluate_p53_test_quality(*, session_state: Mapping[str, Any]) -> GateEvaluationResult:
    """Evaluate P5.3 Test Quality gate.

    Args:
        session_state: Session state.

    Returns:
        GateEvaluationResult with status: 'pass', 'pass-with-exceptions', or 'not-applicable'.
    """
    ticket_digest = str(session_state.get("TicketRecordDigest") or "")
    test_strategy = str(session_state.get("TestStrategy") or "")
    if "not applicable" in ticket_digest.lower() or "not-applicable" in test_strategy.lower():
        return GateEvaluationResult(status="not-applicable")
    return GateEvaluationResult(status="pass")


def evaluate_p54_business_rules(
    *,
    session_state: Mapping[str, Any],
    phase_1_5_executed: bool,
) -> GateEvaluationResult:
    """Evaluate P5.4 Business Rules gate.

    Args:
        session_state: Session state.
        phase_1_5_executed: Whether Phase 1.5 has been executed.

    Returns:
        GateEvaluationResult with status: 'compliant', 'compliant-with-exceptions',
        'not-applicable', or 'gap-detected'.
    """
    br = session_state.get("BusinessRules") or {}
    if not isinstance(br, Mapping):
        return GateEvaluationResult(status="gap-detected")

    validation = br.get("ValidationReport") or {}
    if not isinstance(validation, Mapping) or not validation:
        return GateEvaluationResult(status="gap-detected")

    is_compliant = validation.get("is_compliant", True)
    if not is_compliant:
        return GateEvaluationResult(status="gap-detected")

    return GateEvaluationResult(status="compliant")


def evaluate_p55_technical_debt(*, session_state: Mapping[str, Any]) -> GateEvaluationResult:
    """Evaluate P5.5 Technical Debt gate.

    Args:
        session_state: Session state.

    Returns:
        GateEvaluationResult with status: 'approved', 'rejected', or 'not-applicable'.
    """
    technical_debt_proposed = session_state.get("TechnicalDebtProposed")
    if isinstance(technical_debt_proposed, bool) and technical_debt_proposed:
        return GateEvaluationResult(status="approved")
    return GateEvaluationResult(status="not-applicable")


def evaluate_p56_rollback_safety(*, session_state: Mapping[str, Any]) -> GateEvaluationResult:
    """Evaluate P5.6 Rollback Safety gate.

    Args:
        session_state: Session state.

    Returns:
        GateEvaluationResult with status: 'approved', 'rejected', or 'not-applicable'.
    """
    touched = session_state.get("TouchedSurface") or {}
    if not isinstance(touched, Mapping):
        return GateEvaluationResult(status="not-applicable")

    schema = touched.get("SchemaPlanned")
    contracts = touched.get("ContractsPlanned")
    schema_touched = isinstance(schema, list) and len(schema) > 0
    contracts_touched = isinstance(contracts, list) and len(contracts) > 0

    if not schema_touched and not contracts_touched:
        return GateEvaluationResult(status="not-applicable")

    return GateEvaluationResult(status="approved")
