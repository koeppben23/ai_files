from __future__ import annotations

from governance_runtime.engine.business_rules_hydration import (
    build_business_rules_code_extraction_report,
    build_business_rules_state_snapshot,
)


def test_happy_counter_invariants_hold_across_snapshot_and_code_report() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 7,
            "dropped_candidate_count": 2,
            "candidate_count": 5,
            "validated_code_rule_count": 3,
            "invalid_code_candidate_count": 2,
            "valid_rule_count": 3,
            "invalid_rule_count": 0,
            "count_consistent": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "has_code_coverage_gap": False,
            "has_code_doc_conflict": False,
            "reason_codes": [],
        },
        persistence_result={
            "inventory_written": True,
            "inventory_file_status": "written",
            "report_finalized": True,
        },
    )

    validation_report = snapshot["ValidationReport"]
    code_report = build_business_rules_code_extraction_report(snapshot)

    assert validation_report["raw_candidate_count"] == validation_report["dropped_candidate_count"] + validation_report["candidate_count"]
    assert validation_report["candidate_count"] == validation_report["validated_code_rule_count"] + validation_report["invalid_code_candidate_count"]
    assert code_report["raw_candidate_count"] == code_report["dropped_candidate_count"] + code_report["candidate_count"]
    assert code_report["candidate_count"] == code_report["validated_code_rule_count"] + code_report["invalid_code_candidate_count"]


def test_bad_counter_inputs_are_reconciled_to_consistent_totals() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": False,
            "has_invalid_rules": True,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 2,
            "dropped_candidate_count": 0,
            "candidate_count": 99,
            "validated_code_rule_count": 1,
            "invalid_code_candidate_count": 3,
            "valid_rule_count": 1,
            "invalid_rule_count": 1,
            "count_consistent": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": False,
            "has_code_coverage_gap": True,
            "has_code_doc_conflict": False,
            "reason_codes": ["BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT"],
        },
        persistence_result={
            "inventory_written": False,
            "inventory_file_status": "withheld",
            "report_finalized": True,
        },
    )

    assert snapshot["CandidateCount"] == 4
    assert snapshot["RawCandidateCount"] == 4
    assert snapshot["ValidationReport"]["candidate_count"] == 4
    assert snapshot["ValidationReport"]["raw_candidate_count"] == 4
