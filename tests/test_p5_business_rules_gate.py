from __future__ import annotations

from governance_runtime.engine.gate_evaluator import evaluate_p54_business_rules_gate


def _state_with_validation_report(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "BusinessRules": {
            "Outcome": "extracted",
            "ExecutionEvidence": True,
            "InventoryLoaded": True,
            "ExtractedCount": 2,
            "InvalidRuleCount": 0,
            "DroppedCandidateCount": 0,
            "ValidationReasonCodes": [],
            "ValidationReport": {
                "is_compliant": True,
                "has_invalid_rules": False,
                "has_render_mismatch": False,
                "has_source_violation": False,
                "has_missing_required_rules": False,
                "has_segmentation_failure": False,
                "invalid_rule_count": 0,
                "dropped_candidate_count": 0,
                "count_consistent": True,
            },
        }
    }
    business_rules = base["BusinessRules"]
    assert isinstance(business_rules, dict)
    business_rules.update(overrides)
    return base


def test_happy_p54_compliant_with_full_validation_report() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state=_state_with_validation_report(),
        phase_1_5_executed=True,
    )

    assert result.status == "compliant"
    assert result.validation_report_is_compliant is True
    assert result.invalid_rule_count == 0


def test_bad_p54_blocks_when_invalid_rules_present() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state=_state_with_validation_report(
            InvalidRuleCount=1,
            ValidationReasonCodes=["BUSINESS_RULES_INVALID_CONTENT"],
            ValidationReport={
                "is_compliant": False,
                "has_invalid_rules": True,
                "has_render_mismatch": False,
                "has_source_violation": False,
                "has_missing_required_rules": False,
                "has_segmentation_failure": False,
                "invalid_rule_count": 1,
                "dropped_candidate_count": 0,
                "count_consistent": True,
            },
        ),
        phase_1_5_executed=True,
    )

    assert result.status == "gap-detected"
    assert result.has_invalid_rules is True


def test_corner_p54_blocks_on_render_mismatch() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state=_state_with_validation_report(
            ValidationReasonCodes=["BUSINESS_RULES_RENDER_MISMATCH"],
            ValidationReport={
                "is_compliant": False,
                "has_invalid_rules": False,
                "has_render_mismatch": True,
                "has_source_violation": False,
                "has_missing_required_rules": False,
                "has_segmentation_failure": False,
                "invalid_rule_count": 0,
                "dropped_candidate_count": 1,
                "count_consistent": False,
            },
            DroppedCandidateCount=1,
        ),
        phase_1_5_executed=True,
    )

    assert result.status == "gap-detected"
    assert result.has_render_mismatch is True


def test_edge_p54_not_applicable_without_phase_15() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state={},
        phase_1_5_executed=False,
    )

    assert result.status == "not-applicable"


def test_regression_dropped_candidates_do_not_block_compliant_when_report_is_clean() -> None:
    """Fix regression: dropped non-business candidates are allowed for compliant status."""
    result = evaluate_p54_business_rules_gate(
        session_state=_state_with_validation_report(
            DroppedCandidateCount=7,
            ValidationReport={
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
                "dropped_candidate_count": 7,
                "count_consistent": True,
            },
        ),
        phase_1_5_executed=True,
    )

    assert result.status == "compliant"
    assert result.invalid_rule_count == 0
