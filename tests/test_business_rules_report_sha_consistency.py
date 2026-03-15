from __future__ import annotations

import hashlib
import importlib.util
import json

from governance.engine.business_rules_hydration import build_business_rules_state_snapshot

from .util import REPO_ROOT


def _load_orchestrator_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bad_report_sha_is_derived_from_final_validation_report() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": False,
            "has_invalid_rules": True,
            "has_render_mismatch": True,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 6,
            "dropped_candidate_count": 2,
            "candidate_count": 4,
            "validated_code_rule_count": 1,
            "invalid_code_candidate_count": 3,
            "valid_rule_count": 1,
            "invalid_rule_count": 1,
            "count_consistent": False,
            "has_code_extraction": True,
            "code_extraction_sufficient": False,
            "has_code_coverage_gap": True,
            "has_code_doc_conflict": False,
            "reason_codes": ["BUSINESS_RULES_RENDER_MISMATCH"],
            "coverage_quality_grade": "poor",
        },
        persistence_result={
            "extraction_ran": True,
            "inventory_written": False,
            "inventory_file_status": "withheld",
            "report_finalized": True,
        },
    )

    expected_sha = hashlib.sha256(
        json.dumps(snapshot["ValidationReport"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    assert snapshot["ReportSha"] == expected_sha
    assert snapshot["CodeExtractionReport"]["report_sha"] == expected_sha


def test_edge_status_renderer_emits_same_report_sha_as_snapshot() -> None:
    module = _load_orchestrator_module()
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": True,
            "has_invalid_rules": False,
            "has_render_mismatch": False,
            "has_source_violation": False,
            "has_missing_required_rules": False,
            "has_segmentation_failure": False,
            "raw_candidate_count": 1,
            "dropped_candidate_count": 0,
            "candidate_count": 1,
            "validated_code_rule_count": 1,
            "invalid_code_candidate_count": 0,
            "valid_rule_count": 1,
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
            "inventory_sha256": "b" * 64,
            "report_finalized": True,
        },
    )

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
        code_extraction_run="true",
        code_coverage_sufficient="true",
        code_candidate_count=int(snapshot["CodeCandidateCount"]),
        code_surface_count=int(snapshot["CodeSurfaceCount"]),
        missing_code_surfaces=list(snapshot["MissingCodeSurfaces"]),
        raw_candidate_count=int(snapshot["RawCandidateCount"]),
        candidate_count=int(snapshot["CandidateCount"]),
        validated_code_rule_count=int(snapshot["ValidatedCodeRuleCount"]),
        invalid_code_candidate_count=int(snapshot["InvalidCodeCandidateCount"]),
        report_sha=str(snapshot["ReportSha"]),
    )

    assert f"ReportSha: {snapshot['ReportSha']}" in status
