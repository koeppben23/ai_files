from __future__ import annotations

import importlib.util
from pathlib import Path

from governance_runtime.engine.business_rules_hydration import (
    build_business_rules_code_extraction_report,
    build_business_rules_state_snapshot,
    hydrate_business_rules_state_from_artifacts,
)

from .util import REPO_ROOT


def _load_orchestrator_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_happy_snapshot_drives_status_and_code_report_from_one_truth() -> None:
    module = _load_orchestrator_module()
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 5,
            "dropped_candidate_count": 1,
            "candidate_count": 4,
            "validated_code_rule_count": 2,
            "invalid_code_candidate_count": 2,
            "valid_rule_count": 2,
            "invalid_rule_count": 0,
            "count_consistent": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "code_surface_count": 6,
            "missing_code_surfaces": ["workflow"],
            "has_code_coverage_gap": False,
            "has_code_doc_conflict": False,
            "coverage_quality_grade": "moderate",
            "surface_balance_score": 0.5,
            "semantic_diversity_score": 0.75,
            "quality_insufficiency_reasons": ["workflow_surface_missing"],
            "reason_codes": [],
        },
        persistence_result={
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "execution_evidence": True,
            "inventory_written": True,
            "inventory_loaded": True,
            "inventory_exists": True,
            "inventory_file_status": "written",
            "inventory_file_mode": "update",
            "inventory_sha256": "a" * 64,
            "report_finalized": True,
        },
        code_extraction_report={
            "scanned_file_count": 6,
            "valid_rule_ratio": 0.5,
            "artifact_ratio": 0.0,
            "scanned_surfaces": [{"path": "src/policy.py", "language": "python", "surface_type": "permissions"}],
        },
    )

    code_report = build_business_rules_code_extraction_report(snapshot)
    status = module._render_business_rules_status(
        date="2026-03-15",
        repo_name="demo",
        outcome=str(snapshot["Outcome"]),
        source="ssot-snapshot",
        source_phase=str(snapshot["SourcePhase"]),
        execution_evidence=bool(snapshot["ExecutionEvidence"]),
        extractor_version=str(snapshot["ExtractorVersion"]),
        rules_hash=str(snapshot["Inventory"]["sha256"]),
        validation_result=str(snapshot["ValidationResult"]),
        valid_rules=int(snapshot["ValidRuleCount"]),
        invalid_rules=int(snapshot["InvalidRuleCount"]),
        dropped_candidates=int(snapshot["DroppedCandidateCount"]),
        reason_codes=list(snapshot["ValidationReasonCodes"]),
        render_consistency=str(snapshot["RenderConsistency"]),
        count_consistency=str(snapshot["CountConsistency"]),
        code_extraction_run="true" if bool(snapshot["CodeExtractionRun"]) else "false",
        code_coverage_sufficient="true" if bool(snapshot["CodeCoverageSufficient"]) else "false",
        code_candidate_count=int(snapshot["CodeCandidateCount"]),
        code_surface_count=int(snapshot["CodeSurfaceCount"]),
        missing_code_surfaces=list(snapshot["MissingCodeSurfaces"]),
        raw_candidate_count=int(snapshot["RawCandidateCount"]),
        candidate_count=int(snapshot["CandidateCount"]),
        validated_code_rule_count=int(snapshot["ValidatedCodeRuleCount"]),
        invalid_code_candidate_count=int(snapshot["InvalidCodeCandidateCount"]),
        code_token_artifact_count=int(snapshot["CodeTokenArtifactCount"]),
        template_overfit_count=int(snapshot["TemplateOverfitCount"]),
        coverage_quality_grade=str(snapshot["CoverageQualityGrade"]),
        surface_balance_score=float(snapshot["SurfaceBalanceScore"]),
        semantic_diversity_score=float(snapshot["SemanticDiversityScore"]),
        quality_insufficiency_reasons=list(snapshot["QualityInsufficiencyReasons"]),
        report_sha=str(snapshot["ReportSha"]),
        has_signal=bool(snapshot["HasSignal"]),
    )

    assert snapshot["ValidationReport"]["candidate_count"] == 4
    assert code_report["candidate_count"] == 4
    assert code_report["coverage_quality_grade"] == snapshot["CoverageQualityGrade"]
    assert code_report["surface_balance_score"] == snapshot["SurfaceBalanceScore"]
    assert f"ReportSha: {snapshot['ReportSha']}" in status
    assert "CandidateCount: 4" in status
    assert "CoverageQualityGrade: moderate" in status


def test_corner_hydration_roundtrips_quality_metrics_from_status(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inventory = tmp_path / "business-rules.md"
    _write(
        status,
        "\n".join(
            [
                "Outcome: gap-detected",
                "ExecutionEvidence: true",
                "CodeExtractionRun: true",
                "CodeCoverageSufficient: false",
                "RawCandidateCount: 5",
                "DroppedCandidates: 1",
                "CodeCandidateCount: 4",
                "CandidateCount: 4",
                "ValidatedCodeRuleCount: 1",
                "InvalidCodeCandidateCount: 3",
                "DroppedNonBusinessSurfaceCount: 8",
                "DroppedSchemaOnlyCount: 2",
                "DroppedNonExecutableNormativeTextCount: 1",
                "AcceptedBusinessEnforcementCount: 4",
                "RejectedNonBusinessSubjectCount: 3",
                "CoverageQualityGrade: poor",
                "SurfaceBalanceScore: 0.2",
                "SemanticDiversityScore: 0.1",
                "PostDropValidRatio: 0.25",
                "ExecutableBusinessRuleRatio: 0.20",
                "MissingSurfaceReasons: validator: filtered_non_business, workflow: insufficient_business_context",
                "QualityInsufficiencyReasons: artifact_ratio_above_maximum, semantic_diversity_too_low",
                "ReportSha: 1234abcd",
            ]
        ) + "\n",
    )
    _write(inventory, "- BR-001: Access must be checked\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inventory)

    assert ok is True
    business = state["BusinessRules"]
    assert isinstance(business, dict)
    assert business["CoverageQualityGrade"] == "poor"
    assert business["SurfaceBalanceScore"] == 0.2
    assert business["SemanticDiversityScore"] == 0.1
    validation_report = business["ValidationReport"]
    assert validation_report["dropped_non_business_surface_count"] == 8
    assert validation_report["dropped_schema_only_count"] == 2
    assert validation_report["dropped_non_executable_normative_text_count"] == 1
    assert validation_report["accepted_business_enforcement_count"] == 4
    assert validation_report["rejected_non_business_subject_count"] == 3
    assert validation_report["post_drop_valid_ratio"] == 0.25
    assert validation_report["executable_business_rule_ratio"] == 0.2
    assert validation_report["missing_surface_reasons"] == [
        "validator: filtered_non_business",
        "workflow: insufficient_business_context",
    ]
    assert business["QualityInsufficiencyReasons"] == [
        "artifact_ratio_above_maximum",
        "semantic_diversity_too_low",
    ]


def test_hydration_preserves_discovery_outcomes_materialization() -> None:
    outcomes = [
        {
            "path": "src/a.py",
            "language": "python",
            "line_start": 10,
            "status": "accepted_for_validation",
            "source_text": "BR-C001: Customer must be verified",
            "evidence_snippet": "if not customer_id: raise ValueError",
            "enforcement_anchor_type": "validator",
            "semantic_type": "required-field",
        },
        {
            "path": "src/b.py",
            "language": "python",
            "line_start": 22,
            "status": "dropped_non_business_surface",
            "source_text": "generic payload should be validated",
            "evidence_snippet": "payload.get('x')",
            "enforcement_anchor_type": "",
            "semantic_type": "",
        },
    ]

    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 2,
            "dropped_candidate_count": 1,
            "candidate_count": 1,
            "validated_code_rule_count": 1,
            "invalid_code_candidate_count": 0,
            "valid_rule_count": 1,
            "invalid_rule_count": 0,
            "count_consistent": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "reason_codes": [],
            # stale value must not win
            "discovery_outcomes": [],
        },
        persistence_result={
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "execution_evidence": True,
            "inventory_written": True,
            "inventory_loaded": True,
            "inventory_exists": True,
            "inventory_file_status": "written",
            "inventory_file_mode": "update",
            "inventory_sha256": "a" * 64,
            "report_finalized": True,
        },
        code_extraction_report={
            "raw_candidate_count": 2,
            "candidate_count": 1,
            "dropped_candidate_count": 1,
            "validated_code_rule_count": 1,
            "invalid_code_candidate_count": 0,
            "accepted_business_enforcement_count": 1,
            "discovery_outcomes": outcomes,
        },
    )

    report = snapshot["CodeExtractionReport"]
    assert isinstance(report, dict)
    assert report["raw_candidate_count"] == 2
    assert len(report["discovery_outcomes"]) == 2
    assert report["discovery_outcomes"][0]["path"] == "src/a.py"
    assert report["discovery_outcomes"][-1]["path"] == "src/b.py"


def test_hydration_marks_missing_discovery_outcomes_as_explicit_fallback() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 3,
            "dropped_candidate_count": 1,
            "candidate_count": 2,
            "validated_code_rule_count": 2,
            "invalid_code_candidate_count": 0,
            "valid_rule_count": 2,
            "invalid_rule_count": 0,
            "count_consistent": True,
            "has_code_extraction": True,
            "code_extraction_sufficient": True,
            "reason_codes": [],
        },
        persistence_result={
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "execution_evidence": True,
            "inventory_written": True,
            "inventory_loaded": True,
            "inventory_exists": True,
            "inventory_file_status": "written",
            "inventory_file_mode": "update",
            "inventory_sha256": "a" * 64,
            "report_finalized": True,
        },
        code_extraction_report={
            "raw_candidate_count": 3,
            "candidate_count": 2,
            "dropped_candidate_count": 1,
            "validated_code_rule_count": 2,
            "invalid_code_candidate_count": 0,
            "accepted_business_enforcement_count": 2,
            "discovery_outcomes": [],
        },
    )
    report = snapshot["CodeExtractionReport"]
    assert report["discovery_outcomes"] == []
    assert report["discovery_outcomes_count"] == 3
    assert report["discovery_outcomes_truncated"] is True
