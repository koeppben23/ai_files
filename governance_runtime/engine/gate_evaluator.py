"""Gate evaluation boundary model for Wave A.

The evaluator contract is deterministic and side-effect free so existing
behavior remains unchanged until explicit engine activation in later waves.

Gate checks implemented:
- P5.3 Test Quality Gate: Verifies Phase 4 plan includes Test Strategy
- P5.4 Business Rules Compliance: If Phase 1.5 executed, verify BR coverage
- P5.5 Technical Debt Gate: Always checked — approved or not-applicable pass
- P5.6 Rollback Safety: If schema/contracts touched, verify rollback strategy
- P6 Prerequisites: Verify all upstream gates passed before Phase 6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from governance_runtime.engine.reason_codes import (
    BLOCKED_UNSPECIFIED,
    BLOCKED_P5_3_TEST_QUALITY_GATE,
    BLOCKED_P5_4_BUSINESS_RULES_GATE,
    BLOCKED_P5_5_TECHNICAL_DEBT_GATE,
    BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
    BLOCKED_P6_PLAN_COMPLIANCE_MAJOR,
    BLOCKED_P6_PREREQUISITES_NOT_MET,
    REASON_CODE_NONE,
    WARN_P6_PLAN_COMPLIANCE_DRIFT,
    is_registered_reason_code,
)

from governance_runtime.domain.strict_exit_evaluator import (
    StrictExitResult,
    evaluate_strict_exit,
)

from governance_runtime.application.use_cases.validate_plan_compliance import (
    PlanComplianceReport,
    validate_plan_compliance,
)
from governance_runtime.engine.business_rules_hydration import has_br_signal

GateStatus = Literal["blocked", "warn", "ok", "not_verified"]
P53Status = Literal["pending", "pass", "pass-with-exceptions", "fail", "not-applicable"]
P54Status = Literal["pending", "compliant", "compliant-with-exceptions", "gap-detected", "not-applicable"]
P56Status = Literal["pending", "approved", "rejected", "not-applicable"]
P55Status = Literal["pending", "approved", "rejected", "not-applicable"]
P6Status = Literal["pending", "ready-for-pr", "fix-required"]
P6ComplianceStatus = Literal["compliant", "drift-detected", "major-deviation", "no-plan"]


# ---------------------------------------------------------------------------
# Deterministic gate → reason code mapping (SSOT)
# ---------------------------------------------------------------------------
# Used by evaluate_p6_prerequisites (and indirectly by _normalize_phase6_p5_state
# in session_reader) so that both surfaces derive the blocking reason code from
# the same canonical mapping.
_GATE_TO_REASON_CODE: dict[str, str] = {
    "P5-Architecture": BLOCKED_P6_PREREQUISITES_NOT_MET,  # no gate-specific code for arch
    "P5.3-TestQuality": BLOCKED_P5_3_TEST_QUALITY_GATE,
    "P5.4-BusinessRules": BLOCKED_P5_4_BUSINESS_RULES_GATE,
    "P5.5-TechnicalDebt": BLOCKED_P5_5_TECHNICAL_DEBT_GATE,
    "P5.6-RollbackSafety": BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
}

# Deterministic priority order for P5 prerequisite gate checks.
# This is the single-source-of-truth ordering used by both
# evaluate_p6_prerequisites() and exposed for session_reader normalization.
P5_GATE_PRIORITY_ORDER: tuple[str, ...] = (
    "P5-Architecture",
    "P5.3-TestQuality",
    "P5.4-BusinessRules",
    "P5.5-TechnicalDebt",
    "P5.6-RollbackSafety",
)

# Terminal gate values per gate key (SSOT).
# session_reader._normalize_phase6_p5_state() imports this to avoid
# maintaining a parallel definition.
P5_GATE_TERMINAL_VALUES: dict[str, tuple[str, ...]] = {
    "P5-Architecture": ("approved",),
    "P5.3-TestQuality": ("pass", "pass-with-exceptions", "not-applicable"),
    "P5.4-BusinessRules": ("compliant", "compliant-with-exceptions", "not-applicable"),
    "P5.5-TechnicalDebt": ("approved", "not-applicable"),
    "P5.6-RollbackSafety": ("approved", "not-applicable"),
}


def reason_code_for_gate(gate_key: str) -> str:
    """Return the specific blocking reason code for a P5 gate key.

    Falls back to ``BLOCKED_P6_PREREQUISITES_NOT_MET`` for unknown gates.
    """
    return _GATE_TO_REASON_CODE.get(gate_key, BLOCKED_P6_PREREQUISITES_NOT_MET)


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
    validation_report_is_compliant: bool | None = None
    has_invalid_rules: bool = False
    has_render_mismatch: bool = False
    has_source_violation: bool = False
    has_missing_required_rules: bool = False
    has_segmentation_failure: bool = False
    invalid_rule_count: int = 0
    dropped_candidate_count: int = 0
    quality_reason_codes: tuple[str, ...] = ()
    has_code_extraction: bool = False
    code_extraction_sufficient: bool = False
    code_candidate_count: int = 0
    code_surface_count: int = 0
    missing_code_surfaces: tuple[str, ...] = ()
    has_code_coverage_gap: bool = False
    has_code_doc_conflict: bool = False


@dataclass(frozen=True)
class P55GateEvaluation:
    """Result contract for P5.5 Technical Debt Gate."""

    status: P55Status
    reason_code: str
    technical_debt_proposed: bool


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
    p55_approved: bool | None   # None never used — always checked (not-applicable is terminal)
    p56_approved: bool | None    # None if rollback safety not applicable
    first_open_gate: str | None = None  # deterministic first-open-gate in priority order
    p54_quality_reason_codes: tuple[str, ...] = ()
    p54_code_coverage_gap: bool = False
    p54_missing_code_surfaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class P6PlanComplianceEvaluation:
    """Result contract for plan-vs-implementation compliance at Phase 6 entry.

    Automatically evaluated when entering Phase 6. Compares the persisted
    plan-record against actual implementation evidence.

    Tiered results:
    - compliant: no significant deviations
    - drift-detected: minor deviations (WARN, non-blocking)
    - major-deviation: blocks in pipeline mode, override-able in user mode
    - no-plan: no plan record available (WARN only)
    """

    status: P6ComplianceStatus
    reason_code: str
    report: PlanComplianceReport
    blocked: bool


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

    Engine policy: Phase 4 plan must include a test strategy signal before P5.3 can pass.

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
        if p53_status in ("pass", "pass-with-exceptions", "not-applicable"):
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

    Engine policy:
    - Gate is only applicable if Phase 1.5 was executed.
    - Coverage below minimum threshold yields gap-detected.

    Args:
        session_state: The SESSION_STATE document
        phase_1_5_executed: Whether Phase 1.5 (Business Rules Discovery) was executed

    Returns:
        P54GateEvaluation with status and coverage details.
    """
    business_rules = session_state.get("BusinessRules")
    hydrated_signal = False
    if phase_1_5_executed and isinstance(business_rules, Mapping):
        hydrated_signal = True
    elif isinstance(business_rules, Mapping):
        hydrated_signal = any(
            key in business_rules
            for key in (
                "SourcePhase",
                "ValidationResult",
                "ReportSha",
            )
        )
    source_phase = ""
    if isinstance(business_rules, Mapping):
        source_phase = str(business_rules.get("SourcePhase") or "").strip().lower()
    artifact_phase_signal = source_phase == "1.5-businessrules"

    br_signal = False
    if isinstance(business_rules, Mapping):
        br_signal = has_br_signal(
            declared_outcome=str(business_rules.get("Outcome") or ""),
            report=business_rules.get("ValidationReport") if isinstance(business_rules.get("ValidationReport"), Mapping) else None,
            persistence_result={
                "execution_evidence": business_rules.get("ExecutionEvidence") is True,
                "inventory_loaded": business_rules.get("InventoryLoaded") is True,
                "extracted_count": business_rules.get("ExtractedCount") or 0,
                "validation_signal": bool(str(business_rules.get("ValidationResult") or "").strip()),
                "report_sha_present": bool(str(business_rules.get("ReportSha") or "").strip()),
                "source_phase": str(business_rules.get("SourcePhase") or ""),
            },
        )

    if not phase_1_5_executed and not hydrated_signal and not artifact_phase_signal and not br_signal:
        return P54GateEvaluation(
            status="not-applicable",
            reason_code=REASON_CODE_NONE,
            phase_1_5_executed=False,
            total_business_rules=0,
            covered_business_rules=0,
            uncovered_rules=(),
            validation_report_is_compliant=True,
        )

    if hydrated_signal and isinstance(business_rules, Mapping):
        outcome = str(business_rules.get("Outcome") or "").strip().lower()
        execution_evidence = bool(business_rules.get("ExecutionEvidence") is True)
        inventory_loaded = bool(business_rules.get("InventoryLoaded") is True)

        raw_count = business_rules.get("ExtractedCount")
        if isinstance(raw_count, bool):
            extracted_count = 1 if raw_count else 0
        elif isinstance(raw_count, int):
            extracted_count = raw_count
        elif isinstance(raw_count, str) and raw_count.strip().isdigit():
            extracted_count = int(raw_count.strip())
        else:
            extracted_count = 0

        quality_report = business_rules.get("ValidationReport")
        quality_report_map = quality_report if isinstance(quality_report, Mapping) else {}
        report_is_compliant = bool(quality_report_map.get("is_compliant") is True)
        has_invalid_rules = bool(quality_report_map.get("has_invalid_rules") is True)
        has_render_mismatch = bool(quality_report_map.get("has_render_mismatch") is True)
        has_source_violation = bool(quality_report_map.get("has_source_violation") is True)
        has_missing_required = bool(quality_report_map.get("has_missing_required_rules") is True)
        has_segmentation_failure = bool(quality_report_map.get("has_segmentation_failure") is True)
        has_code_extraction = bool(quality_report_map.get("has_code_extraction", True) is True)
        code_extraction_sufficient = bool(quality_report_map.get("code_extraction_sufficient", True) is True)
        has_code_coverage_gap = bool(quality_report_map.get("has_code_coverage_gap", False) is True)
        has_code_doc_conflict = bool(quality_report_map.get("has_code_doc_conflict", False) is True)
        raw_invalid_count = business_rules.get("InvalidRuleCount") or quality_report_map.get("invalid_rule_count") or 0
        raw_dropped_count = business_rules.get("DroppedCandidateCount") or quality_report_map.get("dropped_candidate_count") or 0
        raw_code_candidate_count = business_rules.get("CodeCandidateCount") or quality_report_map.get("code_candidate_count") or 0
        raw_code_surface_count = business_rules.get("CodeSurfaceCount") or quality_report_map.get("code_surface_count") or 0
        missing_code_surfaces_value = business_rules.get("MissingCodeSurfaces") or quality_report_map.get("missing_code_surfaces") or ()
        try:
            invalid_rule_count = int(raw_invalid_count)
        except (TypeError, ValueError):
            invalid_rule_count = 0
        try:
            dropped_candidate_count = int(raw_dropped_count)
        except (TypeError, ValueError):
            dropped_candidate_count = 0
        try:
            code_candidate_count = int(raw_code_candidate_count)
        except (TypeError, ValueError):
            code_candidate_count = 0
        try:
            code_surface_count = int(raw_code_surface_count)
        except (TypeError, ValueError):
            code_surface_count = 0
        if isinstance(missing_code_surfaces_value, list):
            missing_code_surfaces = tuple(str(x).strip() for x in missing_code_surfaces_value if str(x).strip())
        elif isinstance(missing_code_surfaces_value, str) and missing_code_surfaces_value.strip():
            missing_code_surfaces = tuple(
                x.strip() for x in missing_code_surfaces_value.split(",") if x.strip()
            )
        else:
            missing_code_surfaces = ()
        reason_codes_value = business_rules.get("ValidationReasonCodes")
        quality_reason_codes: tuple[str, ...] = ()
        if isinstance(reason_codes_value, list):
            quality_reason_codes = tuple(str(x).strip() for x in reason_codes_value if str(x).strip())
        elif isinstance(reason_codes_value, str) and reason_codes_value.strip():
            quality_reason_codes = tuple(x.strip() for x in reason_codes_value.split(",") if x.strip())

        # Backward-compat path: legacy snapshots may not have ValidationReport.
        if not quality_report_map:
            report_is_compliant = False
            has_invalid_rules = False
            has_render_mismatch = False
            has_source_violation = True
            has_missing_required = True
            has_segmentation_failure = False
            has_code_extraction = False
            code_extraction_sufficient = False
            has_code_coverage_gap = True
            has_code_doc_conflict = False
            invalid_rule_count = 0
            dropped_candidate_count = 0
            code_candidate_count = 0
            code_surface_count = 0
            missing_code_surfaces = ()
            quality_reason_codes = ("BUSINESS_RULES_CODE_EXTRACTION_NOT_RUN",)

        if outcome == "extracted":
            if (
                execution_evidence
                and inventory_loaded
                and extracted_count > 0
                and report_is_compliant
                and not has_invalid_rules
                and not has_render_mismatch
                and not has_source_violation
                and not has_missing_required
                and not has_segmentation_failure
                and has_code_extraction
                and code_extraction_sufficient
                and not has_code_coverage_gap
                and not has_code_doc_conflict
                and invalid_rule_count == 0
                # Fix 2.1: dropped_candidate_count reflects legitimately filtered
                # non-business candidates (e.g. non_business_surface_spike).
                # A high drop count with 0 invalid rules is normal and must not
                # block compliant status.
            ):
                return P54GateEvaluation(
                    status="compliant",
                    reason_code=REASON_CODE_NONE,
                    phase_1_5_executed=True,
                    total_business_rules=extracted_count,
                    covered_business_rules=extracted_count,
                    uncovered_rules=(),
                    validation_report_is_compliant=True,
                    has_invalid_rules=False,
                    has_render_mismatch=False,
                    has_source_violation=False,
                    has_missing_required_rules=False,
                    has_segmentation_failure=False,
                    invalid_rule_count=0,
                    dropped_candidate_count=0,
                    quality_reason_codes=quality_reason_codes,
                    has_code_extraction=has_code_extraction,
                    code_extraction_sufficient=code_extraction_sufficient,
                    code_candidate_count=max(code_candidate_count, 0),
                    code_surface_count=max(code_surface_count, 0),
                    missing_code_surfaces=missing_code_surfaces,
                    has_code_coverage_gap=has_code_coverage_gap,
                    has_code_doc_conflict=has_code_doc_conflict,
                )
            return P54GateEvaluation(
                status="gap-detected",
                reason_code=BLOCKED_P5_4_BUSINESS_RULES_GATE,
                phase_1_5_executed=True,
                total_business_rules=max(extracted_count, 0),
                covered_business_rules=0,
                uncovered_rules=("business-rules-hydration-incomplete",),
                validation_report_is_compliant=report_is_compliant,
                has_invalid_rules=has_invalid_rules,
                has_render_mismatch=has_render_mismatch,
                has_source_violation=has_source_violation,
                has_missing_required_rules=has_missing_required,
                has_segmentation_failure=has_segmentation_failure,
                invalid_rule_count=max(invalid_rule_count, 0),
                dropped_candidate_count=max(dropped_candidate_count, 0),
                quality_reason_codes=quality_reason_codes,
                has_code_extraction=has_code_extraction,
                code_extraction_sufficient=code_extraction_sufficient,
                code_candidate_count=max(code_candidate_count, 0),
                code_surface_count=max(code_surface_count, 0),
                missing_code_surfaces=missing_code_surfaces,
                has_code_coverage_gap=has_code_coverage_gap,
                has_code_doc_conflict=has_code_doc_conflict,
            )

        if outcome in {"not-applicable", "deferred", "skipped"}:
            has_strict_artifact_signal = bool(br_signal)
            if not has_strict_artifact_signal:
                return P54GateEvaluation(
                    status="not-applicable",
                    reason_code=REASON_CODE_NONE,
                    phase_1_5_executed=True,
                    total_business_rules=0,
                    covered_business_rules=0,
                    uncovered_rules=(),
                    validation_report_is_compliant=True,
                )
            return P54GateEvaluation(
                status="gap-detected",
                reason_code=BLOCKED_P5_4_BUSINESS_RULES_GATE,
                phase_1_5_executed=True,
                total_business_rules=0,
                covered_business_rules=0,
                uncovered_rules=("business-rules-applicability-inconsistent",),
                validation_report_is_compliant=False,
                has_invalid_rules=has_invalid_rules,
                has_render_mismatch=has_render_mismatch,
                has_source_violation=has_source_violation,
                has_missing_required_rules=has_missing_required,
                has_segmentation_failure=has_segmentation_failure,
                invalid_rule_count=max(invalid_rule_count, 0),
                dropped_candidate_count=max(dropped_candidate_count, 0),
                quality_reason_codes=quality_reason_codes,
                has_code_extraction=has_code_extraction,
                code_extraction_sufficient=code_extraction_sufficient,
                code_candidate_count=max(code_candidate_count, 0),
                code_surface_count=max(code_surface_count, 0),
                missing_code_surfaces=missing_code_surfaces,
                has_code_coverage_gap=has_code_coverage_gap,
                has_code_doc_conflict=has_code_doc_conflict,
            )

        if outcome in {"gap-detected", "unresolved"}:
            return P54GateEvaluation(
                status="gap-detected",
                reason_code=BLOCKED_P5_4_BUSINESS_RULES_GATE,
                phase_1_5_executed=True,
                total_business_rules=max(extracted_count, 0),
                covered_business_rules=0,
                uncovered_rules=("business-rules-validation-failed",),
                validation_report_is_compliant=report_is_compliant,
                has_invalid_rules=has_invalid_rules,
                has_render_mismatch=has_render_mismatch,
                has_source_violation=has_source_violation,
                has_missing_required_rules=has_missing_required,
                has_segmentation_failure=has_segmentation_failure,
                invalid_rule_count=max(invalid_rule_count, 0),
                dropped_candidate_count=max(dropped_candidate_count, 0),
                quality_reason_codes=quality_reason_codes,
                has_code_extraction=has_code_extraction,
                code_extraction_sufficient=code_extraction_sufficient,
                code_candidate_count=max(code_candidate_count, 0),
                code_surface_count=max(code_surface_count, 0),
                missing_code_surfaces=missing_code_surfaces,
                has_code_coverage_gap=has_code_coverage_gap,
                has_code_doc_conflict=has_code_doc_conflict,
            )

    # Legacy/fallback behavior for rule-list based states.
    total_rules = 0
    covered_rules = 0
    uncovered: list[str] = []

    if isinstance(business_rules, Mapping):
        rules_list = business_rules.get("Rules") or business_rules.get("rules")
        if isinstance(rules_list, list):
            for rule in rules_list:
                if isinstance(rule, Mapping):
                    has_rule_id = False
                    for key in ("id", "BR-ID"):
                        value = rule.get(key)
                        if isinstance(value, str) and value.strip():
                            has_rule_id = True
                            break
                    has_coverage_signal = any(
                        key in rule for key in ("covered", "implemented", "tested")
                    )
                    if not has_rule_id and not has_coverage_signal:
                        continue
                    total_rules += 1
                    rule_id = rule.get("id") or rule.get("BR-ID") or ""
                    covered = rule.get("covered") or rule.get("implemented") or rule.get("tested")
                    if covered is True or covered == "true":
                        covered_rules += 1
                    else:
                        uncovered.append(str(rule_id))
                elif isinstance(rule, str):
                    total_rules += 1
                    covered_rules += 1

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

    if total_rules == 0:
        coverage_pct = 100.0
    else:
        coverage_pct = (covered_rules / total_rules) * 100

    if coverage_pct < 70.0:
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

    Engine policy:
    - If schema/contracts are touched, rollback strategy must be present and actionable.
    - If migration is not reversible, explicit safety steps are required.

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


def evaluate_p55_technical_debt_gate(
    *,
    session_state: Mapping[str, object],
) -> P55GateEvaluation:
    """Evaluate P5.5 Technical Debt Gate.

    Engine policy:
    - Always checked (not conditional).
    - Gate status ``"approved"`` or ``"not-applicable"`` are terminal pass states.
    - ``"rejected"`` blocks Phase 6 promotion.

    Args:
        session_state: The SESSION_STATE document

    Returns:
        P55GateEvaluation with status and details.
    """
    # Check whether technical debt was proposed at all
    technical_debt_proposed = False
    for key in ("TechnicalDebtProposed", "technical_debt_proposed"):
        value = session_state.get(key)
        if isinstance(value, bool):
            technical_debt_proposed = value
            break
    if not technical_debt_proposed:
        technical_debt = session_state.get("TechnicalDebt")
        if isinstance(technical_debt, Mapping):
            proposed = technical_debt.get("Proposed")
            if isinstance(proposed, bool):
                technical_debt_proposed = proposed

    # Check existing P5.5 gate status
    gates = session_state.get("Gates")
    if isinstance(gates, Mapping):
        p55_status = gates.get("P5.5-TechnicalDebt")
        if p55_status == "approved":
            return P55GateEvaluation(
                status="approved",
                reason_code=REASON_CODE_NONE,
                technical_debt_proposed=technical_debt_proposed,
            )
        if p55_status == "not-applicable":
            return P55GateEvaluation(
                status="not-applicable",
                reason_code=REASON_CODE_NONE,
                technical_debt_proposed=technical_debt_proposed,
            )
        if p55_status == "rejected":
            return P55GateEvaluation(
                status="rejected",
                reason_code=BLOCKED_P5_5_TECHNICAL_DEBT_GATE,
                technical_debt_proposed=technical_debt_proposed,
            )

    # No explicit gate status yet — if no technical debt was proposed,
    # the gate is not-applicable (terminal pass).
    if not technical_debt_proposed:
        return P55GateEvaluation(
            status="not-applicable",
            reason_code=REASON_CODE_NONE,
            technical_debt_proposed=False,
        )

    # Technical debt proposed but gate not yet evaluated → pending
    return P55GateEvaluation(
        status="pending",
        reason_code=REASON_CODE_NONE,
        technical_debt_proposed=True,
    )


def evaluate_p6_prerequisites(
    *,
    session_state: Mapping[str, object],
    phase_1_5_executed: bool,
    rollback_safety_applies: bool,
) -> P6PrerequisiteEvaluation:
    """Evaluate P6 Implementation QA prerequisites.

    Engine policy:
    - P5-Architecture must be approved.
    - P5.3-TestQuality must be pass or pass-with-exceptions.
    - If Phase 1.5 executed: P5.4-BusinessRules must be compliant or compliant-with-exceptions.
    - P5.5-TechnicalDebt must be approved or not-applicable (always checked).
    - If rollback safety applies: P5.6-RollbackSafety must be approved or not-applicable.

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
            p55_approved=False,
            p56_approved=None,
            p54_quality_reason_codes=(),
            p54_code_coverage_gap=False,
            p54_missing_code_surfaces=(),
        )

    # P5-Architecture must be approved
    p5_arch = gates.get("P5-Architecture")
    p5_architecture_approved = p5_arch == "approved"

    # P5.3-TestQuality must be pass, pass-with-exceptions, or not-applicable
    p53 = gates.get("P5.3-TestQuality")
    p53_passed = p53 in ("pass", "pass-with-exceptions", "not-applicable")

    # P5.4-BusinessRules (only if Phase 1.5 executed)
    p54_compliant: bool | None = None
    p54_quality_reason_codes: tuple[str, ...] = ()
    p54_code_coverage_gap = False
    p54_missing_code_surfaces: tuple[str, ...] = ()
    if phase_1_5_executed:
        p54_eval = evaluate_p54_business_rules_gate(
            session_state=session_state,
            phase_1_5_executed=True,
        )
        p54_compliant = p54_eval.status in ("compliant", "compliant-with-exceptions", "not-applicable")
        p54_quality_reason_codes = tuple(getattr(p54_eval, "quality_reason_codes", ()) or ())
        p54_code_coverage_gap = bool(getattr(p54_eval, "has_code_coverage_gap", False))
        p54_missing_code_surfaces = tuple(getattr(p54_eval, "missing_code_surfaces", ()) or ())

    # P5.5-TechnicalDebt (always checked — "approved" or "not-applicable" pass)
    p55 = gates.get("P5.5-TechnicalDebt")
    p55_approved = p55 in ("approved", "not-applicable")

    # P5.6-RollbackSafety (only if rollback safety applies)
    p56_approved: bool | None = None
    if rollback_safety_applies:
        p56 = gates.get("P5.6-RollbackSafety")
        p56_approved = p56 in ("approved", "not-applicable")

    # Check all prerequisites
    all_passed = p5_architecture_approved and p53_passed and p55_approved
    if phase_1_5_executed and p54_compliant is not None:
        all_passed = all_passed and p54_compliant
    if rollback_safety_applies and p56_approved is not None:
        all_passed = all_passed and p56_approved

    if not all_passed:
        # Determine the first open gate in deterministic priority order:
        # P5-Architecture → P5.3 → P5.4 → P5.5 → P5.6
        first_open: str | None = None
        if not p5_architecture_approved:
            first_open = "P5-Architecture"
        elif not p53_passed:
            first_open = "P5.3-TestQuality"
        elif phase_1_5_executed and p54_compliant is not None and not p54_compliant:
            first_open = "P5.4-BusinessRules"
        elif not p55_approved:
            first_open = "P5.5-TechnicalDebt"
        elif rollback_safety_applies and p56_approved is not None and not p56_approved:
            first_open = "P5.6-RollbackSafety"

        # Use the gate-specific blocking reason code (SSOT via
        # _GATE_TO_REASON_CODE) so callers can surface a precise blocker
        # without re-interpreting first_open_gate themselves.
        blocking_reason = reason_code_for_gate(first_open) if first_open else BLOCKED_P6_PREREQUISITES_NOT_MET

        return P6PrerequisiteEvaluation(
            passed=False,
            reason_code=blocking_reason,
            p5_architecture_approved=p5_architecture_approved,
            p53_passed=p53_passed,
            p54_compliant=p54_compliant,
            p55_approved=p55_approved,
            p56_approved=p56_approved,
            first_open_gate=first_open,
            p54_quality_reason_codes=p54_quality_reason_codes,
            p54_code_coverage_gap=p54_code_coverage_gap,
            p54_missing_code_surfaces=p54_missing_code_surfaces,
        )

    return P6PrerequisiteEvaluation(
        passed=True,
        reason_code=REASON_CODE_NONE,
        p5_architecture_approved=p5_architecture_approved,
        p53_passed=p53_passed,
        p54_compliant=p54_compliant,
        p55_approved=p55_approved,
        p56_approved=p56_approved,
        p54_quality_reason_codes=p54_quality_reason_codes,
        p54_code_coverage_gap=p54_code_coverage_gap,
        p54_missing_code_surfaces=p54_missing_code_surfaces,
    )


def can_promote_to_phase6(
    *,
    session_state: Mapping[str, object],
    phase_1_5_executed: bool,
    rollback_safety_applies: bool,
) -> tuple[bool, P6PrerequisiteEvaluation]:
    """Single source of truth wrapper for Phase 6 promotion eligibility.

    Returns ``(can_promote, evaluation)`` — the caller should use the
    ``P6PrerequisiteEvaluation`` for detail logging / blocking reasons.
    """
    evaluation = evaluate_p6_prerequisites(
        session_state=session_state,
        phase_1_5_executed=phase_1_5_executed,
        rollback_safety_applies=rollback_safety_applies,
    )
    return evaluation.passed, evaluation


def evaluate_p6_plan_compliance(
    *,
    plan_record: Mapping[str, object] | None,
    actual_files_changed: list[str],
    actual_contracts_changed: list[str] | None = None,
    test_files_found: list[str] | None = None,
    mode: str = "user",
) -> P6PlanComplianceEvaluation:
    """Evaluate plan-vs-implementation compliance at Phase 6 entry.

    Runs automatically when entering Phase 6.  Compares the persisted
    plan-record (touched_surface, test_strategy, contracts) against actual
    implementation evidence.

    Only precise checks are performed (files, contracts, tests).  No
    heuristic checks (rollback, NFR) to avoid false positives.

    Tiered enforcement:
    - Pipeline mode: ``major-deviation`` is a hard block.
    - User mode: ``major-deviation`` is a WARN (override-able).
    - ``drift-detected`` and ``no-plan`` are always WARN only.

    Args:
        plan_record: The loaded plan-record.json dict (or None).
        actual_files_changed: Files actually changed (e.g. from git diff).
        actual_contracts_changed: API/contract files changed (optional).
        test_files_found: Test files found in the changeset (optional).
        mode: Operating mode (``"user"`` or ``"pipeline"``).

    Returns:
        P6PlanComplianceEvaluation with status, reason code, full report,
        and blocked flag.
    """
    report = validate_plan_compliance(
        plan_record=plan_record,
        actual_files_changed=actual_files_changed,
        actual_contracts_changed=actual_contracts_changed,
        test_files_found=test_files_found,
    )

    status: P6ComplianceStatus = report.status  # type: ignore[assignment]

    if status == "compliant":
        return P6PlanComplianceEvaluation(
            status="compliant",
            reason_code=REASON_CODE_NONE,
            report=report,
            blocked=False,
        )

    if status == "no-plan":
        return P6PlanComplianceEvaluation(
            status="no-plan",
            reason_code=WARN_P6_PLAN_COMPLIANCE_DRIFT,
            report=report,
            blocked=False,
        )

    if status == "major-deviation":
        is_pipeline = mode.strip().lower() == "pipeline"
        return P6PlanComplianceEvaluation(
            status="major-deviation",
            reason_code=BLOCKED_P6_PLAN_COMPLIANCE_MAJOR if is_pipeline else WARN_P6_PLAN_COMPLIANCE_DRIFT,
            report=report,
            blocked=is_pipeline,
        )

    # drift-detected
    return P6PlanComplianceEvaluation(
        status="drift-detected",
        reason_code=WARN_P6_PLAN_COMPLIANCE_DRIFT,
        report=report,
        blocked=False,
    )


def evaluate_strict_exit_gate(
    *,
    pass_criteria: list[Mapping[str, object]],
    evidence_map: Mapping[str, Mapping[str, object]],
    risk_tier: str = "unknown",
    principal_strict: bool,
) -> StrictExitResult:
    """Engine-layer entry point for the strict-exit gate.

    Integrates after P5.3/P5.4/P5.6/P6 gates, before phase transition.
    Only blocks when ``principal_strict`` is ``True`` and critical evidence
    criteria fail.
    """
    from datetime import datetime, timezone

    return evaluate_strict_exit(
        pass_criteria=pass_criteria,
        evidence_map=evidence_map,
        risk_tier=risk_tier,
        now_utc=datetime.now(timezone.utc),
        principal_strict=principal_strict,
    )
