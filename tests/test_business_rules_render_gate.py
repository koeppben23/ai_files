from __future__ import annotations

from governance.engine.business_rules_hydration import build_business_rules_state_snapshot


def test_failed_validation_never_resolves_to_extracted() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": False,
            "valid_rule_count": 3,
            "invalid_rule_count": 1,
            "dropped_candidate_count": 0,
            "count_consistent": False,
            "has_render_mismatch": True,
            "has_invalid_rules": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": False,
            "has_code_coverage_gap": True,
            "has_code_doc_conflict": False,
            "reason_codes": ["BUSINESS_RULES_RENDER_MISMATCH"],
        },
        persistence_result={
            "extraction_ran": True,
            "inventory_written": False,
            "inventory_file_status": "withheld",
        },
    )

    assert snapshot["Outcome"] == "gap-detected"
    assert snapshot["ValidationResult"] == "failed"
    assert snapshot["InventoryLoaded"] is False


def test_extracted_requires_written_inventory_and_full_compliance() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "valid_rule_count": 2,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 0,
            "count_consistent": True,
            "has_render_mismatch": False,
            "has_invalid_rules": False,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "has_code_coverage_gap": False,
            "has_code_doc_conflict": False,
            "reason_codes": [],
        },
        persistence_result={
            "extraction_ran": True,
            "inventory_written": True,
            "inventory_file_status": "written",
            "inventory_sha256": "a" * 64,
        },
    )

    assert snapshot["Outcome"] == "extracted"
    assert snapshot["ValidationResult"] == "passed"
    assert snapshot["ExtractedCount"] == 2
    assert snapshot["InventoryLoaded"] is True
