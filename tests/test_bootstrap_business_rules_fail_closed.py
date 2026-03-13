from __future__ import annotations

from governance.engine.business_rules_hydration import build_business_rules_state_snapshot


def test_fail_closed_snapshot_for_low_quality_extraction() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": False,
            "valid_rule_count": 0,
            "invalid_rule_count": 300,
            "dropped_candidate_count": 400,
            "raw_candidate_count": 4096,
            "count_consistent": False,
            "has_render_mismatch": True,
            "has_invalid_rules": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": False,
            "code_candidate_count": 4096,
            "code_surface_count": 455,
            "has_code_coverage_gap": True,
            "has_code_doc_conflict": False,
            "has_code_token_artifacts": True,
            "has_quality_insufficiency": True,
            "reason_codes": [
                "BUSINESS_RULES_CODE_TOKEN_ARTIFACT",
                "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT",
            ],
        },
        persistence_result={
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "inventory_written": False,
            "inventory_file_status": "withheld",
        },
    )

    assert snapshot["Outcome"] == "gap-detected"
    assert snapshot["ValidationResult"] == "failed"
    assert snapshot["InventoryLoaded"] is False
    assert snapshot["CodeCoverageSufficient"] is False
