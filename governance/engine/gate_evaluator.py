"""Gate evaluation boundary model for Wave A.

The evaluator contract is deterministic and side-effect free so existing
behavior remains unchanged until explicit engine activation in later waves.

Gate checks implemented:
- P5.3 Test Quality Gate: Verifies Phase 4 plan includes Test Strategy
- P5.4 Business Rules Compliance: If Phase 1.5 executed, verify BR coverage
- P5.6 Rollback Safety: If schema/contracts touched, verify rollback strategy
- P6 Prerequisites: Verify all upstream gates passed before Phase 6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from governance.engine.reason_codes import (
    BLOCKED_UNSPECIFIED,
    BLOCKED_P5_3_TEST_QUALITY_GATE,
    BLOCKED_P5_4_BUSINESS_RULES_GATE,
    BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
    BLOCKED_P6_PREREQUISITES_NOT_MET,
    REASON_CODE_NONE,
    is_registered_reason_code,
)

GateStatus = Literal["blocked", "warn", "ok", "not_verified"]
P53Status = Literal["pending", "pass", "pass-with-exceptions", "fail"]
P54Status = Literal["pending", "compliant", "compliant-with-exceptions", "gap-detected", "not-applicable"]
P56Status = Literal["pending", "approved", "rejected", "not-applicable"]
P6Status = Literal["pending", "ready-for-pr", "fix-required"]


@dataclass(frozen=True)
class GateEvaluation:
    """Result contract for one gate evaluation."""

    gate_key: str
    status: GateStatus
    reason_code: str


@dataclass(frozen=True)
class P53GateEvaluation:
    """Result contract for P5.3 Test Quality Gate."""

    status: P53Status
    reason_code: str
    missing_test_strategy: bool
    coverage_gaps: tuple[str, ...]


@dataclass(frozen=True)
class P54GateEvaluation:
    """Result contract for P5.4 Business Rules Compliance Gate."""

    status: P54Status
    reason_code: str
    phase_1_5_executed: bool
    total_business_rules: int
    covered_business_rules: int
    uncovered_rules: tuple[str, ...]


@dataclass(frozen=True)
class P56GateEvaluation:
    """Result contract for P5.6 Rollback Safety Gate."""

    status: P56Status
    reason_code: str
    schema_touched: bool
    contracts_touched: bool
    rollback_strategy_present: bool
    rollback_reversible: bool


@dataclass(frozen=True)
class P6PrerequisiteEvaluation:
    """Result contract for P6 prerequisite checks."""

    passed: bool
    reason_code: str
    p5_architecture_approved: bool
    p53_passed: bool
    p54_compliant: bool | None  # None if Phase 1.5 not executed
    p56_approved: bool | None    # None if rollback safety not applicable


def evaluate_gate(
    *,
    gate_key: str,
    blocked: bool,
    reason_code: str = REASON_CODE_NONE,
    enforce_registered_reason_code: bool = False,
) -> GateEvaluation:
    """Build deterministic gate evaluation output from explicit inputs.

    When `enforce_registered_reason_code=True`, the evaluator fail-closes unknown
    blocked reason codes to `BLOCKED-UNSPECIFIED`.
    """

    normalized_key = gate_key.strip()
    if blocked:
        rc = reason_code.strip() or BLOCKED_UNSPECIFIED
        if enforce_registered_reason_code and not is_registered_reason_code(rc, allow_none=False):
            rc = BLOCKED_UNSPECIFIED
        return GateEvaluation(gate_key=normalized_key, status="blocked", reason_code=rc)
    return GateEvaluation(gate_key=normalized_key, status="ok", reason_code=REASON_CODE_NONE)


def evaluate_p53_test_quality_gate(
    *,
    session_state: Mapping[str, object],
) -> P53GateEvaluation:
    """Evaluate P5.3 Test Quality Gate.

    Binding prerequisite from master.md line 3290:
    "The Phase 4 plan MUST include a Test Strategy subsection. If missing → BLOCK
    and return to Phase 4."

    Args:
        session_state: The SESSION_STATE document (the SESSION_STATE key, not the wrapper)

    Returns:
        P53GateEvaluation with status and details.
    """
    # Check for TicketRecordDigest which contains the Phase 4 plan
    ticket_record = session_state.get("TicketRecordDigest")
    nfr_checklist = session_state.get("NFRChecklist")

    # Look for test strategy indicators
    test_strategy_present = False
    if isinstance(ticket_record, str):
        test_strategy_present = "Test Strategy" in ticket_record or "test strategy" in ticket_record.lower()

    # Also check NFRChecklist for test requirements
    if not test_strategy_present and isinstance(nfr_checklist, Mapping):
        test_section = nfr_checklist.get("Testing") or nfr_checklist.get("test")
        if test_section:
            test_strategy_present = True

    # Check for explicit TestStrategy field
    test_strategy = session_state.get("TestStrategy")
    if test_strategy:
        test_strategy_present = True

    if not test_strategy_present:
        return P53GateEvaluation(
            status="fail",
            reason_code=BLOCKED_P5_3_TEST_QUALITY_GATE,
            missing_test_strategy=True,
            coverage_gaps=("Missing Test Strategy subsection in Phase 4 plan",),
        )

    # Check existing P5.3 gate status if already evaluated
    gates = session_state.get("Gates")
    if isinstance(gates, Mapping):
        p53_status = gates.get("P5.3-TestQuality")
        if p53_status in ("pass", "pass-with-exceptions"):
            return P53GateEvaluation(
                status=p53_status,
                reason_code=REASON_CODE_NONE,
                missing_test_strategy=False,
                coverage_gaps=(),
            )

    # Default to pending if test strategy present but not yet evaluated
    return P53GateEvaluation(
        status="pending",
        reason_code=REASON_CODE_NONE,
        missing_test_strategy=False,
        coverage_gaps=(),
    )


def evaluate_p54_business_rules_gate(
    *,
    session_state: Mapping[str, object],
    phase_1_5_executed: bool,
) -> P54GateEvaluation:
    """Evaluate P5.4 Business Rules Compliance Gate.

    From master.md lines 3389-3521:
    - Gate is only applicable if Phase 1.5 was executed.
    - If >30% of business rules are uncovered → gap-detected

    Args:
        session_state: The SESSION_STATE document
        phase_1_5_executed: Whether Phase 1.5 (Business Rules Discovery) was executed

    Returns:
        P54GateEvaluation with status and coverage details.
    """
    if not phase_1_5_executed:
        return P54GateEvaluation(
            status="not-applicable",
            reason_code=REASON_CODE_NONE,
            phase_1_5_executed=False,
            total_business_rules=0,
            covered_business_rules=0,
            uncovered_rules=(),
        )

    # Extract business rules from session state
    business_rules = session_state.get("BusinessRules")
    total_rules = 0
    covered_rules = 0
    uncovered: list[str] = []

    if isinstance(business_rules, Mapping):
        rules_list = business_rules.get("Rules") or business_rules.get("rules")
        if isinstance(rules_list, list):
            total_rules = len(rules_list)
            for rule in rules_list:
                if isinstance(rule, Mapping):
                    rule_id = rule.get("id") or rule.get("BR-ID") or ""
                    covered = rule.get("covered") or rule.get("implemented") or rule.get("tested")
                    if covered is True or covered == "true":
                        covered_rules += 1
                    else:
                        uncovered.append(str(rule_id))
                elif isinstance(rule, str):
                    total_rules += 1
                    # Assume covered if string (no coverage info)
                    covered_rules += 1

    # Check existing P5.4 gate status
    gates = session_state.get("Gates")
    if isinstance(gates, Mapping):
        p54_status = gates.get("P5.4-BusinessRules")
        if p54_status in ("compliant", "compliant-with-exceptions"):
            return P54GateEvaluation(
                status=p54_status,
                reason_code=REASON_CODE_NONE,
                phase_1_5_executed=True,
                total_business_rules=total_rules,
                covered_business_rules=covered_rules,
                uncovered_rules=tuple(uncovered),
            )

    # Calculate coverage percentage
    if total_rules == 0:
        coverage_pct = 100.0
    else:
        coverage_pct = (covered_rules / total_rules) * 100

    # Gate rule: if >30% uncovered → gap-detected
    if coverage_pct < 70:
        return P54GateEvaluation(
            status="gap-detected",
            reason_code=BLOCKED_P5_4_BUSINESS_RULES_GATE,
            phase_1_5_executed=True,
            total_business_rules=total_rules,
            covered_business_rules=covered_rules,
            uncovered_rules=tuple(uncovered),
        )

    return P54GateEvaluation(
        status="pending",
        reason_code=REASON_CODE_NONE,
        phase_1_5_executed=True,
        total_business_rules=total_rules,
        covered_business_rules=covered_rules,
        uncovered_rules=tuple(uncovered),
    )


def evaluate_p56_rollback_safety_gate(
    *,
    session_state: Mapping[str, object],
) -> P56GateEvaluation:
    """Evaluate P5.6 Rollback Safety Gate.

    From master.md lines 3112-3119:
    - If TouchedSurface.SchemaPlanned is non-empty OR ContractsPlanned suggests
      consumer impact, ensure RollbackStrategy is present and actionable.
    - If RollbackStrategy.DataMigrationReversible = false, require explicit safety steps.

    Args:
        session_state: The SESSION_STATE document

    Returns:
        P56GateEvaluation with status and details.
    """
    # Check TouchedSurface
    touched_surface = session_state.get("TouchedSurface")
    schema_touched = False
    contracts_touched = False

    if isinstance(touched_surface, Mapping):
        schema_planned = touched_surface.get("SchemaPlanned")
        if isinstance(schema_planned, list) and len(schema_planned) > 0:
            schema_touched = True
        contracts_planned = touched_surface.get("ContractsPlanned")
        if isinstance(contracts_planned, list) and len(contracts_planned) > 0:
            contracts_touched = True

    # If nothing touched that requires rollback safety
    if not schema_touched and not contracts_touched:
        return P56GateEvaluation(
            status="not-applicable",
            reason_code=REASON_CODE_NONE,
            schema_touched=False,
            contracts_touched=False,
            rollback_strategy_present=False,
            rollback_reversible=True,
        )

    # Check RollbackStrategy
    rollback_strategy = session_state.get("RollbackStrategy")
    rollback_present = rollback_strategy is not None
    rollback_reversible = True

    if isinstance(rollback_strategy, Mapping):
        reversible = rollback_strategy.get("DataMigrationReversible")
        if reversible is False:
            rollback_reversible = False

    # Check existing P5.6 gate status
    gates = session_state.get("Gates")
    if isinstance(gates, Mapping):
        p56_status = gates.get("P5.6-RollbackSafety")
        if p56_status == "approved":
            return P56GateEvaluation(
                status="approved",
                reason_code=REASON_CODE_NONE,
                schema_touched=schema_touched,
                contracts_touched=contracts_touched,
                rollback_strategy_present=rollback_present,
                rollback_reversible=rollback_reversible,
            )

    # If rollback strategy missing when needed
    if not rollback_present:
        return P56GateEvaluation(
            status="rejected",
            reason_code=BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
            schema_touched=schema_touched,
            contracts_touched=contracts_touched,
            rollback_strategy_present=False,
            rollback_reversible=False,
        )

    # If data migration not reversible, require explicit safety steps
    if not rollback_reversible:
        # Check for explicit safety steps
        safety_steps = session_state.get("RollbackSafetySteps")
        if not safety_steps:
            return P56GateEvaluation(
                status="rejected",
                reason_code=BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
                schema_touched=schema_touched,
                contracts_touched=contracts_touched,
                rollback_strategy_present=True,
                rollback_reversible=False,
            )

    return P56GateEvaluation(
        status="pending",
        reason_code=REASON_CODE_NONE,
        schema_touched=schema_touched,
        contracts_touched=contracts_touched,
        rollback_strategy_present=rollback_present,
        rollback_reversible=rollback_reversible,
    )


def evaluate_p6_prerequisites(
    *,
    session_state: Mapping[str, object],
    phase_1_5_executed: bool,
    rollback_safety_applies: bool,
) -> P6PrerequisiteEvaluation:
    """Evaluate P6 Implementation QA prerequisites.

    From master.md lines 3686-3691:
    - P5-Architecture MUST be approved.
    - P5.3-TestQuality MUST be pass or pass-with-exceptions.
    - If Phase 1.5 executed: P5.4-BusinessRules MUST be compliant or compliant-with-exceptions.
    - If rollback safety applies: P5.6-RollbackSafety MUST be approved or not-applicable.

    Args:
        session_state: The SESSION_STATE document
        phase_1_5_executed: Whether Phase 1.5 was executed
        rollback_safety_applies: Whether rollback safety conditions exist

    Returns:
        P6PrerequisiteEvaluation with pass/fail and details.
    """
    gates = session_state.get("Gates")
    if not isinstance(gates, Mapping):
        return P6PrerequisiteEvaluation(
            passed=False,
            reason_code=BLOCKED_P6_PREREQUISITES_NOT_MET,
            p5_architecture_approved=False,
            p53_passed=False,
            p54_compliant=None,
            p56_approved=None,
        )

    # P5-Architecture must be approved
    p5_arch = gates.get("P5-Architecture")
    p5_architecture_approved = p5_arch == "approved"

    # P5.3-TestQuality must be pass or pass-with-exceptions
    p53 = gates.get("P5.3-TestQuality")
    p53_passed = p53 in ("pass", "pass-with-exceptions")

    # P5.4-BusinessRules (only if Phase 1.5 executed)
    p54_compliant: bool | None = None
    if phase_1_5_executed:
        p54 = gates.get("P5.4-BusinessRules")
        p54_compliant = p54 in ("compliant", "compliant-with-exceptions")

    # P5.6-RollbackSafety (only if rollback safety applies)
    p56_approved: bool | None = None
    if rollback_safety_applies:
        p56 = gates.get("P5.6-RollbackSafety")
        p56_approved = p56 in ("approved", "not-applicable")

    # Check all prerequisites
    all_passed = p5_architecture_approved and p53_passed
    if phase_1_5_executed and p54_compliant is not None:
        all_passed = all_passed and p54_compliant
    if rollback_safety_applies and p56_approved is not None:
        all_passed = all_passed and p56_approved

    if not all_passed:
        return P6PrerequisiteEvaluation(
            passed=False,
            reason_code=BLOCKED_P6_PREREQUISITES_NOT_MET,
            p5_architecture_approved=p5_architecture_approved,
            p53_passed=p53_passed,
            p54_compliant=p54_compliant,
            p56_approved=p56_approved,
        )

    return P6PrerequisiteEvaluation(
        passed=True,
        reason_code=REASON_CODE_NONE,
        p5_architecture_approved=p5_architecture_approved,
        p53_passed=p53_passed,
        p54_compliant=p54_compliant,
        p56_approved=p56_approved,
    )
