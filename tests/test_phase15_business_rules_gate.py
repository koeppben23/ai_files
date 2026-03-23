from __future__ import annotations

from governance_runtime.engine.gate_evaluator import evaluate_p54_business_rules_gate


def _state_with_report(report: dict[str, object]) -> dict[str, object]:
    def _as_int(value: object) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return 0

    return {
        "BusinessRules": {
            "Outcome": "extracted",
            "ExecutionEvidence": True,
            "InventoryLoaded": True,
            "ExtractedCount": 2,
            "InvalidRuleCount": _as_int(report.get("invalid_rule_count") or 0),
            "DroppedCandidateCount": _as_int(report.get("dropped_candidate_count") or 0),
            "ValidationReasonCodes": report.get("reason_codes") or [],
            "ValidationReport": report,
            "CodeCandidateCount": _as_int(report.get("code_candidate_count") or 0),
            "CodeSurfaceCount": _as_int(report.get("code_surface_count") or 0),
            "MissingCodeSurfaces": report.get("missing_code_surfaces") or [],
        }
    }


def test_happy_gate_passes_with_code_extraction_sufficient() -> None:
    state = _state_with_report(
        {
            "is_compliant": True,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "has_code_coverage_gap": False,
            "has_code_doc_conflict": False,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 0,
            "code_candidate_count": 3,
            "code_surface_count": 5,
            "missing_code_surfaces": [],
        }
    )

    result = evaluate_p54_business_rules_gate(session_state=state, phase_1_5_executed=True)

    assert result.status == "compliant"
    assert result.has_code_extraction is True
    assert result.code_extraction_sufficient is True


def test_bad_gate_blocks_when_code_extraction_not_run() -> None:
    state = _state_with_report(
        {
            "is_compliant": False,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "has_code_extraction": False,
            "code_extraction_sufficient": False,
            "has_code_coverage_gap": True,
            "has_code_doc_conflict": False,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 0,
            "code_candidate_count": 0,
            "code_surface_count": 0,
            "missing_code_surfaces": ["validator"],
            "reason_codes": ["BUSINESS_RULES_CODE_EXTRACTION_NOT_RUN"],
        }
    )

    result = evaluate_p54_business_rules_gate(session_state=state, phase_1_5_executed=True)

    assert result.status == "gap-detected"
    assert result.has_code_extraction is False
    assert result.has_code_coverage_gap is True


def test_corner_gate_blocks_on_code_coverage_gap() -> None:
    state = _state_with_report(
        {
            "is_compliant": False,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "has_code_extraction": True,
            "code_extraction_sufficient": False,
            "has_code_coverage_gap": True,
            "has_code_doc_conflict": False,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 1,
            "code_candidate_count": 0,
            "code_surface_count": 4,
            "missing_code_surfaces": ["permissions", "workflow"],
            "reason_codes": ["BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT"],
        }
    )

    result = evaluate_p54_business_rules_gate(session_state=state, phase_1_5_executed=True)

    assert result.status == "gap-detected"
    assert result.code_extraction_sufficient is False
    assert result.code_surface_count == 4


def test_edge_gate_blocks_on_doc_code_conflict() -> None:
    state = _state_with_report(
        {
            "is_compliant": False,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "has_code_coverage_gap": False,
            "has_code_doc_conflict": True,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 0,
            "code_candidate_count": 2,
            "code_surface_count": 2,
            "missing_code_surfaces": [],
            "reason_codes": ["BUSINESS_RULES_CODE_DOC_CONFLICT"],
        }
    )

    result = evaluate_p54_business_rules_gate(session_state=state, phase_1_5_executed=True)

    assert result.status == "gap-detected"
    assert result.has_code_doc_conflict is True


def test_bad_legacy_snapshot_without_validation_report_is_fail_closed() -> None:
    state = {
        "BusinessRules": {
            "Outcome": "extracted",
            "ExecutionEvidence": True,
            "InventoryLoaded": True,
            "ExtractedCount": 2,
            "InvalidRuleCount": 0,
            "DroppedCandidateCount": 0,
        }
    }

    result = evaluate_p54_business_rules_gate(session_state=state, phase_1_5_executed=True)

    assert result.status == "gap-detected"
    assert result.has_code_extraction is False
    assert result.code_extraction_sufficient is False
    assert "BUSINESS_RULES_CODE_EXTRACTION_NOT_RUN" in result.quality_reason_codes
