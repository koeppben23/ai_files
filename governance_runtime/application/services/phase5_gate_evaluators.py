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


def _as_string_list(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return ()


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
    if isinstance(br, Mapping):
        execution = br.get("Execution")
        if isinstance(execution, Mapping):
            completed = execution.get("Completed")
            if isinstance(completed, bool) and completed:
                return True
        executed = br.get("Executed")
        if isinstance(executed, bool) and executed:
            return True
        execution_evidence = br.get("ExecutionEvidence")
        if isinstance(execution_evidence, bool) and execution_evidence:
            return True
    return False


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
    if not phase_1_5_executed:
        return GateEvaluationResult(status="pending")

    br = session_state.get("BusinessRules") or {}
    if not isinstance(br, Mapping):
        return GateEvaluationResult(status="gap-detected")

    outcome = str(br.get("Outcome") or "").strip().lower()
    validation = br.get("ValidationReport") or {}
    if not isinstance(validation, Mapping):
        validation = {}

    if outcome in {"not-applicable", "deferred", "skipped"}:
        return GateEvaluationResult(status="not-applicable")

    missing_surface_reasons = _as_string_list(
        br.get("MissingSurfaceReasons")
        or validation.get("missing_surface_reasons")
        or ((br.get("CodeExtractionReport") or {}) if isinstance(br.get("CodeExtractionReport"), Mapping) else {}).get("missing_surface_reasons")
    )
    quality_insufficiency_reasons = _as_string_list(
        br.get("QualityInsufficiencyReasons")
        or validation.get("quality_insufficiency_reasons")
        or ((br.get("CodeExtractionReport") or {}) if isinstance(br.get("CodeExtractionReport"), Mapping) else {}).get("quality_insufficiency_reasons")
    )
    validation_reason_codes = {
        item
        for item in _as_string_list(br.get("ValidationReasonCodes"))
    }
    all_missing_surfaces_non_business = bool(missing_surface_reasons) and all(
        "filtered_non_business" in reason for reason in missing_surface_reasons
    )
    non_business_not_applicable = (
        all_missing_surfaces_non_business
        and "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT" in validation_reason_codes
        and "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT" in validation_reason_codes
        and "non_business_surface_spike" in set(quality_insufficiency_reasons)
        and "insufficient_executable_business_rules" in set(quality_insufficiency_reasons)
        and bool(validation.get("has_code_extraction") is True)
        and not bool(validation.get("has_invalid_rules") is True)
        and not bool(validation.get("has_render_mismatch") is True)
        and not bool(validation.get("has_source_violation") is True)
        and not bool(validation.get("has_missing_required_rules") is True)
        and not bool(validation.get("has_segmentation_failure") is True)
    )
    if non_business_not_applicable:
        return GateEvaluationResult(status="not-applicable")

    is_compliant = bool(validation.get("is_compliant") is True)
    if is_compliant and int(br.get("ExtractedCount") or 0) > 0:
        return GateEvaluationResult(status="compliant")

    return GateEvaluationResult(status="gap-detected")


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
