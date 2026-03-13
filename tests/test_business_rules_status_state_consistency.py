from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from governance.engine.business_rules_hydration import build_business_rules_state_snapshot

from .util import REPO_ROOT


def _load_orchestrator_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_status_and_session_state_use_same_snapshot_truth(tmp_path: Path) -> None:
    module = _load_orchestrator_module()
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": False,
            "valid_rule_count": 0,
            "invalid_rule_count": 2,
            "dropped_candidate_count": 1,
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
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "inventory_written": False,
            "inventory_file_status": "withheld",
        },
    )

    status = module._render_business_rules_status(
        date="2026-03-13",
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
        raw_candidate_count=int(snapshot["ValidationReport"]["raw_candidate_count"]),
        report_sha=str(snapshot["ReportSha"]),
    )

    assert "Outcome: gap-detected" in status
    assert "ValidationResult: failed" in status

    session_path = tmp_path / "SESSION_STATE.json"
    session_path.write_text(json.dumps({"SESSION_STATE": {"Scope": {}, "BusinessRules": {}}}) + "\n", encoding="utf-8")
    result = module._update_session_state(
        session_path=session_path,
        dry_run=False,
        extractor_ran=True,
        extracted_rule_count=0,
        extraction_evidence=True,
        business_rules_inventory_action="withheld",
        repo_cache_action="kept",
        repo_map_digest_action="kept",
        decision_pack_action="kept",
        workspace_memory_action="kept",
        business_rules_inventory_sha256="",
        business_rules_rules=[],
        business_rules_source_phase="1.5-BusinessRules",
        business_rules_extractor_version="hybrid-br-v1",
        business_rules_evidence_paths=[],
        read_only=False,
        business_rules_snapshot=snapshot,
    )
    assert result == "updated"
    persisted = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]["BusinessRules"]
    assert persisted["Outcome"] == snapshot["Outcome"]
    assert persisted["ValidationResult"] == snapshot["ValidationResult"]
    assert persisted["InvalidRuleCount"] == snapshot["InvalidRuleCount"]
    assert persisted["DroppedCandidateCount"] == snapshot["DroppedCandidateCount"]
    assert persisted["ValidationReasonCodes"] == snapshot["ValidationReasonCodes"]
