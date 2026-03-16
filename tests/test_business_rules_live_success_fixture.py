from __future__ import annotations

from pathlib import Path

from governance.engine.business_rules_hydration import build_business_rules_state_snapshot
from governance.engine.business_rules_validation import extract_validated_business_rules_with_diagnostics


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_live_success_fixture_produces_extracted_outcome(tmp_path: Path) -> None:
    # Block F: Live-success fixture must have proper business rules
    # that pass stricter validation - use clean doc-origin rules
    _write(
        tmp_path / "docs" / "business-rules.md",
        "# Business Rules\n"
        "- BR-100: Access must be authenticated before write operations\n"
        "- BR-101: Audit entries must remain immutable after persistence\n"
        "- BR-102: Customer orders must be validated before processing\n"
        "- BR-103: Payment amounts must be verified for all transactions\n",
    )
    # Add minimal code surfaces that won't trigger governance checks
    _write(
        tmp_path / "src" / "policy.py",
        "def authorize(user):\n"
        "    if not user.can_write:\n"
        "        raise PermissionError('unauthorized')\n",
    )
    _write(
        tmp_path / "src" / "validator.py",
        "def validate(payload):\n"
        "    if not payload.get('customer_id'):\n"
        "        raise ValueError('required field')\n",
    )
    _write(
        tmp_path / "src" / "workflow.py",
        "def transition(status):\n"
        "    if status == 'archived':\n"
        "        raise RuntimeError('invalid transition')\n",
    )

    report, _, ok = extract_validated_business_rules_with_diagnostics(tmp_path)
    assert ok is True
    
    # Verify the new stricter validation still produces valid rules
    # With doc-origin rules, we should have valid rules regardless of code validation
    assert report.valid_rule_count >= 2, f"Expected >= 2 valid rules, got {report.valid_rule_count}"
    
    # Build snapshot
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": report.is_compliant,
            "has_invalid_rules": report.has_invalid_rules,
            "has_render_mismatch": report.has_render_mismatch,
            "has_source_violation": report.has_source_violation,
            "has_missing_required_rules": report.has_missing_required_rules,
            "has_segmentation_failure": report.has_segmentation_failure,
            "raw_candidate_count": report.raw_candidate_count,
            "segmented_candidate_count": report.segmented_candidate_count,
            "valid_rule_count": report.valid_rule_count,
            "invalid_rule_count": report.invalid_rule_count,
            "dropped_candidate_count": report.dropped_candidate_count,
            "count_consistent": True,
            "has_code_extraction": report.has_code_extraction,
            "code_extraction_sufficient": report.code_extraction_sufficient,
            "code_candidate_count": report.code_candidate_count,
            "code_surface_count": report.code_surface_count,
            "missing_code_surfaces": list(report.missing_code_surfaces),
            "has_code_coverage_gap": report.has_code_coverage_gap,
            "has_code_doc_conflict": report.has_code_doc_conflict,
            "has_code_token_artifacts": report.has_code_token_artifacts,
            "has_quality_insufficiency": report.has_quality_insufficiency,
            "invalid_code_candidate_count": report.invalid_code_candidate_count,
            "code_token_artifact_count": report.code_token_artifact_count,
            "artifact_ratio_exceeded": report.artifact_ratio_exceeded,
            "artifact_ratio": report.artifact_ratio,
            "reason_codes": list(report.reason_codes),
        },
        persistence_result={
            "declared_outcome": "extracted",
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "execution_evidence": True,
            "inventory_written": True,
            "inventory_loaded": True,
            "inventory_exists": True,
            "status_file_present": True,
            "validation_signal": True,
            "report_sha_present": True,
            "inventory_file_status": "written",
            "inventory_file_mode": "update",
            "inventory_sha256": "f" * 64,
            "report_finalized": True,
        },
    )

    # Block F: Strong assertions - doc-origin rules should pass through
    assert snapshot["Outcome"] == "extracted"
    assert snapshot["ValidationResult"] == "passed"
    assert snapshot["ValidRuleCount"] >= 2
    assert snapshot["InventoryFileStatus"] == "written"
