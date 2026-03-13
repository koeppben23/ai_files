from __future__ import annotations

from governance.engine.business_rules_hydration import build_business_rules_state_snapshot


def test_success_snapshot_for_valid_business_rules_inventory() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "valid_rule_count": 5,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 0,
            "raw_candidate_count": 20,
            "count_consistent": True,
            "has_render_mismatch": False,
            "has_invalid_rules": False,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "code_candidate_count": 12,
            "code_surface_count": 8,
            "has_code_coverage_gap": False,
            "has_code_doc_conflict": False,
            "has_code_token_artifacts": False,
            "has_quality_insufficiency": False,
            "reason_codes": [],
        },
        persistence_result={
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "inventory_written": True,
            "inventory_file_status": "written",
            "inventory_sha256": "b" * 64,
        },
    )

    assert snapshot["Outcome"] == "extracted"
    assert snapshot["ValidationResult"] == "passed"
    assert snapshot["ExtractedCount"] == 5
    assert snapshot["InventoryLoaded"] is True
