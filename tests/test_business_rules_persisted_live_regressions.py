from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from governance.engine.business_rules_hydration import (
    build_business_rules_code_extraction_report,
    build_business_rules_state_snapshot,
    hydrate_business_rules_state_from_artifacts,
)
from governance.engine.business_rules_validation import ValidationReport, extract_validated_business_rules_with_diagnostics

from .util import REPO_ROOT


def _load_orchestrator_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _parse_status_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _parse_reason_field(value: str) -> list[str]:
    token = str(value or "").strip()
    if not token or token.lower() == "none":
        return []
    return [item.strip() for item in token.split(",") if item.strip()]


def _report_input(report: ValidationReport) -> dict[str, object]:
    return {
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
        "count_consistent": report.count_consistent,
        "has_code_extraction": report.has_code_extraction,
        "code_extraction_sufficient": report.code_extraction_sufficient,
        "code_candidate_count": report.code_candidate_count,
        "validated_code_rule_count": report.code_valid_rule_count,
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
        "template_overfit_count": report.template_overfit_count,
        "reason_codes": list(report.reason_codes),
        "source_diagnostics": list(report.source_diagnostics),
    }


def _persist_artifacts(
    *,
    workspace: Path,
    report: ValidationReport,
    code_payload: dict[str, object],
    declared_outcome: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, str], dict[str, object], Path]:
    module = _load_orchestrator_module()
    session_path = workspace / "SESSION_STATE.json"
    _write(session_path, json.dumps({"SESSION_STATE": {"Scope": {}, "BusinessRules": {}}}, ensure_ascii=True) + "\n")

    rules = [row.text for row in report.valid_rules]
    evidence_paths = [f"{row.source_path}:{row.line_no}" for row in report.valid_rules]
    inventory_path = workspace / "business-rules.md"

    inventory_written = declared_outcome == "extracted"
    inventory_sha = "0" * 64
    if inventory_written:
        inventory_content = module._render_business_rules_inventory_extracted(
            date="2026-03-15",
            repo_name="demo",
            rules=rules,
            evidence_paths=evidence_paths,
            extractor_version="hybrid-br-v1",
        )
        _write(inventory_path, inventory_content)
        normalized = inventory_content if inventory_content.endswith("\n") else inventory_content + "\n"
        inventory_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    else:
        inventory_path.unlink(missing_ok=True)

    snapshot = build_business_rules_state_snapshot(
        report=_report_input(report),
        persistence_result={
            "declared_outcome": declared_outcome,
            "source_phase": "1.5-BusinessRules",
            "extractor_version": "hybrid-br-v1",
            "extraction_source": "deterministic",
            "extraction_ran": True,
            "execution_evidence": True,
            "inventory_written": inventory_written,
            "inventory_loaded": inventory_written,
            "inventory_exists": inventory_written,
            "status_file_present": True,
            "validation_signal": True,
            "report_sha_present": True,
            "inventory_file_status": "written" if inventory_written else "withheld",
            "inventory_file_mode": "update" if inventory_written else "unknown",
            "inventory_sha256": inventory_sha,
            "report_finalized": True,
        },
        code_extraction_report=code_payload,
    )
    code_report = build_business_rules_code_extraction_report(snapshot)

    status_content = module._render_business_rules_status(
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
        source_diagnostics=list((snapshot.get("ValidationReport") or {}).get("source_diagnostics", [])) if isinstance(snapshot.get("ValidationReport"), dict) else [],
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
    status_path = workspace / "business-rules-status.md"
    _write(status_path, status_content)

    code_report_path = workspace / ".governance" / "business_rules" / "code_extraction_report.json"
    _write(code_report_path, json.dumps(code_report, ensure_ascii=True, indent=2) + "\n")

    result = module._update_session_state(
        session_path=session_path,
        dry_run=False,
        extractor_ran=True,
        extracted_rule_count=len(rules),
        extraction_evidence=True,
        business_rules_inventory_action="created" if inventory_written else "withheld",
        repo_cache_action="kept",
        repo_map_digest_action="kept",
        decision_pack_action="kept",
        workspace_memory_action="kept",
        business_rules_inventory_sha256=inventory_sha,
        business_rules_rules=rules,
        business_rules_source_phase="1.5-BusinessRules",
        business_rules_extractor_version="hybrid-br-v1",
        business_rules_evidence_paths=evidence_paths,
        read_only=False,
        business_rules_snapshot=snapshot,
    )
    assert result == "updated"

    persisted_state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]["BusinessRules"]
    return snapshot, code_report, _parse_status_fields(status_content), persisted_state, inventory_path


def test_live_fail_fixture_persists_fail_closed_artifacts(tmp_path: Path) -> None:
    # These files should NOT produce valid business rules - they use generic helper
    # functions with no enforcement anchors that would pass stricter validation
    _write(
        tmp_path / "src" / "helper.py",
        "def helper(x):\n"
        "    return x + 1\n",
    )
    _write(
        tmp_path / "src" / "util.py",
        "def util(data):\n"
        "    return data.upper()\n",
    )
    _write(
        tmp_path / "src" / "tool.py",
        "def tool(item):\n"
        "    return item.name\n",
    )

    report, diagnostics, ok = extract_validated_business_rules_with_diagnostics(tmp_path)
    assert ok is True
    code_payload = diagnostics.get("code_extraction")
    assert isinstance(code_payload, dict)

    snapshot, code_report, status_fields, persisted_state, inventory_path = _persist_artifacts(
        workspace=tmp_path,
        report=report,
        code_payload=code_payload,
        declared_outcome="gap-detected",
    )

    assert inventory_path.exists() is False
    assert snapshot["Outcome"] == "gap-detected"
    assert persisted_state["Outcome"] == "gap-detected"
    assert persisted_state["ValidationResult"] == "failed"
    assert persisted_state["CodeCoverageSufficient"] is False
    assert status_fields["outcome"] == "gap-detected"
    assert status_fields["validationresult"] == "failed"
    assert status_fields["codecoveragesufficient"] == "false"
    assert status_fields["reportsha"] == str(snapshot["ReportSha"])
    assert code_report["report_sha"] == str(snapshot["ReportSha"])
    assert code_report["is_sufficient"] is False


def test_live_success_fixture_persists_extracted_artifacts_with_ssot_invariants(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "business-rules.md",
        "# Business Rules\n"
        "- BR-100: Access must be authenticated before write operations\n"
        "- BR-101: Audit entries must remain immutable after persistence\n",
    )
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

    report, diagnostics, ok = extract_validated_business_rules_with_diagnostics(tmp_path)
    assert ok is True
    code_payload = diagnostics.get("code_extraction")
    assert isinstance(code_payload, dict)

    snapshot, code_report, status_fields, persisted_state, inventory_path = _persist_artifacts(
        workspace=tmp_path,
        report=report,
        code_payload=code_payload,
        declared_outcome="extracted",
    )

    assert inventory_path.exists() is True
    assert snapshot["Outcome"] == "extracted"
    assert persisted_state["Outcome"] == "extracted"
    assert persisted_state["ValidationResult"] == "passed"
    assert persisted_state["CodeCoverageSufficient"] is True
    assert status_fields["outcome"] == "extracted"
    assert status_fields["validationresult"] == "passed"
    assert status_fields["reportsha"] == str(snapshot["ReportSha"])
    assert code_report["report_sha"] == str(snapshot["ReportSha"])

    assert int(status_fields["rawcandidatecount"]) == int(persisted_state["RawCandidateCount"])
    assert int(status_fields["candidatecount"]) == int(persisted_state["CandidateCount"])
    assert int(status_fields["validatedcoderulecount"]) == int(persisted_state["ValidatedCodeRuleCount"])
    assert int(status_fields["invalidcodecandidatecount"]) == int(persisted_state["InvalidCodeCandidateCount"])
    assert int(status_fields["droppedcandidates"]) == int(persisted_state["DroppedCandidateCount"])
    assert int(status_fields["rawcandidatecount"]) == int(code_report["raw_candidate_count"])
    assert int(status_fields["candidatecount"]) == int(code_report["candidate_count"])
    assert int(status_fields["validatedcoderulecount"]) == int(code_report["validated_code_rule_count"])
    assert int(status_fields["invalidcodecandidatecount"]) == int(code_report["invalid_code_candidate_count"])
    assert int(status_fields["rawcandidatecount"]) == int(status_fields["droppedcandidates"]) + int(status_fields["candidatecount"])
    assert int(status_fields["candidatecount"]) == int(status_fields["validatedcoderulecount"]) + int(status_fields["invalidcodecandidatecount"])

    assert persisted_state["CoverageQualityGrade"] == code_report["coverage_quality_grade"]
    assert float(status_fields["surfacebalancescore"]) == float(persisted_state["SurfaceBalanceScore"])
    assert float(status_fields["semanticdiversityscore"]) == float(persisted_state["SemanticDiversityScore"])
    assert _parse_reason_field(status_fields["qualityinsufficiencyreasons"]) == list(persisted_state["QualityInsufficiencyReasons"])

    hydrated_state: dict[str, object] = {}
    applied = hydrate_business_rules_state_from_artifacts(
        state=hydrated_state,
        status_path=tmp_path / "business-rules-status.md",
        inventory_path=inventory_path,
    )
    assert applied is True
    hydrated_business = hydrated_state["BusinessRules"]
    assert isinstance(hydrated_business, dict)
    assert hydrated_business["ReportSha"] == persisted_state["ReportSha"]
    assert hydrated_business["CoverageQualityGrade"] == persisted_state["CoverageQualityGrade"]
