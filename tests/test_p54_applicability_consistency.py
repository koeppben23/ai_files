from __future__ import annotations

from governance_runtime.engine.gate_evaluator import evaluate_p54_business_rules_gate


def test_p54_not_not_applicable_when_phase15_artifact_signal_exists() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state={
            "BusinessRules": {
                "Outcome": "gap-detected",
                "SourcePhase": "1.5-BusinessRules",
                "ValidationResult": "failed",
                "ExecutionEvidence": True,
            }
        },
        phase_1_5_executed=False,
    )
    assert result.status == "gap-detected"


def test_p54_failed_validation_maps_to_gap_detected() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state={
            "BusinessRules": {
                "Outcome": "gap-detected",
                "ExecutionEvidence": True,
                "InventoryLoaded": False,
                "ExtractedCount": 0,
                "ValidationReport": {
                    "is_compliant": False,
                    "has_invalid_rules": True,
                    "has_render_mismatch": True,
                    "count_consistent": False,
                    "has_code_extraction": True,
                    "code_extraction_sufficient": False,
                    "has_code_coverage_gap": True,
                },
            }
        },
        phase_1_5_executed=True,
    )
    assert result.status == "gap-detected"


def test_p54_passed_validation_maps_to_compliant() -> None:
    result = evaluate_p54_business_rules_gate(
        session_state={
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 1,
                "ValidationReport": {
                    "is_compliant": True,
                    "has_invalid_rules": False,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "count_consistent": True,
                    "has_code_extraction": True,
                    "code_extraction_sufficient": True,
                    "has_code_coverage_gap": False,
                    "has_code_doc_conflict": False,
                },
                "InvalidRuleCount": 0,
                "DroppedCandidateCount": 0,
            }
        },
        phase_1_5_executed=True,
    )
    assert result.status == "compliant"
