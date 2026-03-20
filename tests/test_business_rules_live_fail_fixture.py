from __future__ import annotations

from pathlib import Path

from governance_runtime.engine.business_rules_hydration import build_business_rules_state_snapshot
from governance_runtime.engine.business_rules_validation import extract_validated_business_rules_with_diagnostics


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_live_fail_fixture_is_fail_closed_with_withheld_inventory(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "policy.py",
        "if blocked:\n"
        "    raise PermissionError('forbidden')\n"
        "# Permission checks must be enforced for archived_files\n",
    )
    _write(
        tmp_path / "src" / "validation.py",
        "if not payload:\n"
        "    raise ValueError('required')\n"
        "# Required field checks must be enforced for from dataclasses import dataclass\n",
    )
    _write(
        tmp_path / "src" / "workflow.py",
        "if status == 'archived':\n"
        "    raise RuntimeError('invalid transition')\n"
        "# Permission checks must be enforced for src/workflow.py\n",
    )

    report, _, ok = extract_validated_business_rules_with_diagnostics(tmp_path)
    assert ok is True
    
    # Block F: fail fixture may still produce valid extracted candidates,
    # but downstream status forcing mismatch must remain fail-closed.

    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": report.is_compliant,
            "has_invalid_rules": report.has_invalid_rules,
            "has_render_mismatch": True,
            "has_source_violation": report.has_source_violation,
            "has_missing_required_rules": report.has_missing_required_rules,
            "has_segmentation_failure": report.has_segmentation_failure,
            "raw_candidate_count": report.raw_candidate_count,
            "segmented_candidate_count": report.segmented_candidate_count,
            "valid_rule_count": report.valid_rule_count,
            "invalid_rule_count": report.invalid_rule_count,
            "dropped_candidate_count": report.dropped_candidate_count,
            "count_consistent": False,
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
            "declared_outcome": "gap-detected",
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "execution_evidence": True,
            "inventory_written": False,
            "inventory_loaded": False,
            "inventory_exists": False,
            "status_file_present": True,
            "validation_signal": True,
            "report_sha_present": True,
            "inventory_file_status": "withheld",
            "inventory_file_mode": "unknown",
            "inventory_sha256": "0" * 64,
            "report_finalized": True,
        },
    )

    assert snapshot["Outcome"] == "gap-detected"
    assert snapshot["ValidationResult"] == "failed"
    assert snapshot["CodeCoverageSufficient"] is False
    assert snapshot["ValidationReport"]["has_quality_insufficiency"] is True
    assert snapshot["InventoryFileStatus"] == "withheld"
