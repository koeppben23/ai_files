from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from governance.engine.business_rules_validation import validate_inventory_markdown

_RESOLVED_OUTCOMES = {"extracted", "gap-detected", "unresolved", "not-applicable", "deferred", "skipped"}


def _parse_bool(token: str) -> bool:
    value = token.strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _parse_status_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_token = key.strip().lower()
        if not key_token:
            continue
        fields[key_token] = value.strip()
    return fields


def _parse_csv_reasons(token: str) -> list[str]:
    if not token:
        return []
    out: list[str] = []
    for part in token.split(","):
        probe = part.strip()
        if probe:
            out.append(probe)
    return out


def _parse_int(token: str, default: int = 0) -> int:
    probe = str(token or "").strip()
    if not probe:
        return default
    try:
        return int(probe)
    except ValueError:
        return default


def _normalize_reason_codes(value: object) -> list[str]:
    if isinstance(value, str):
        return _parse_csv_reasons(value)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _truthy(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return _parse_bool(str(value))


def _build_report_sha(report: Mapping[str, Any]) -> str:
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_business_rules_state_snapshot(
    *,
    report: Mapping[str, Any],
    persistence_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the canonical BusinessRules state snapshot (SSOT).

    This snapshot is the single source for both SESSION_STATE.BusinessRules and
    business-rules-status.md rendering.
    """

    report_map = dict(report)
    valid_rule_count = max(_parse_int(str(report_map.get("valid_rule_count", 0))), 0)
    invalid_rule_count = max(_parse_int(str(report_map.get("invalid_rule_count", 0))), 0)
    dropped_candidate_count = max(_parse_int(str(report_map.get("dropped_candidate_count", 0))), 0)
    raw_candidate_count = max(_parse_int(str(report_map.get("raw_candidate_count", 0))), 0)
    code_candidate_count = max(_parse_int(str(report_map.get("code_candidate_count", 0))), 0)
    code_surface_count = max(_parse_int(str(report_map.get("code_surface_count", 0))), 0)
    code_extraction_sufficient = _truthy(report_map.get("code_extraction_sufficient"), default=False)
    has_code_extraction = _truthy(report_map.get("has_code_extraction"), default=False)
    has_invalid_rules = _truthy(report_map.get("has_invalid_rules"), default=False)
    has_code_coverage_gap = _truthy(report_map.get("has_code_coverage_gap"), default=not code_extraction_sufficient)
    has_code_doc_conflict = _truthy(report_map.get("has_code_doc_conflict"), default=False)
    has_code_token_artifacts = _truthy(report_map.get("has_code_token_artifacts"), default=False)
    has_quality_insufficiency = _truthy(report_map.get("has_quality_insufficiency"), default=False)
    artifact_ratio_exceeded = _truthy(report_map.get("artifact_ratio_exceeded"), default=False)
    has_render_mismatch = _truthy(report_map.get("has_render_mismatch"), default=False)
    count_consistent = _truthy(report_map.get("count_consistent"), default=False)
    render_consistent = not has_render_mismatch
    report_is_compliant = _truthy(report_map.get("is_compliant"), default=False)
    reason_codes = sorted(set(_normalize_reason_codes(report_map.get("reason_codes"))))
    inventory_written = _truthy(persistence_result.get("inventory_written"), default=True)
    declared_outcome = str(persistence_result.get("declared_outcome") or "").strip().lower()

    extracted_allowed = (
        report_is_compliant
        and valid_rule_count > 0
        and render_consistent
        and count_consistent
        and not has_invalid_rules
        and not has_code_coverage_gap
        and not has_code_doc_conflict
        and not has_code_token_artifacts
        and not has_quality_insufficiency
        and not artifact_ratio_exceeded
        and has_code_extraction
        and code_extraction_sufficient
        and inventory_written
    )

    extraction_ran = _truthy(persistence_result.get("extraction_ran"), default=has_code_extraction)
    compatibility_outcome_allowed = declared_outcome in {"not-applicable", "deferred", "skipped"}
    if extracted_allowed:
        outcome = "extracted"
    elif compatibility_outcome_allowed:
        outcome = declared_outcome
    elif extraction_ran:
        outcome = "gap-detected"
    else:
        outcome = "unresolved"

    inventory_file_status = str(persistence_result.get("inventory_file_status") or "unknown").strip() or "unknown"
    inventory_file_mode = str(persistence_result.get("inventory_file_mode") or "unknown").strip() or "unknown"
    inventory_sha256 = str(persistence_result.get("inventory_sha256") or "").strip() or ("0" * 64)
    inventory_loaded = bool(outcome == "extracted" and inventory_file_status == "written")
    extracted_count = valid_rule_count if outcome == "extracted" else 0
    validation_result = "passed" if (extracted_allowed or compatibility_outcome_allowed) else "failed"

    normalized_report: dict[str, Any] = {
        "is_compliant": report_is_compliant,
        "has_invalid_rules": has_invalid_rules,
        "has_render_mismatch": has_render_mismatch,
        "has_source_violation": _truthy(report_map.get("has_source_violation"), default=False),
        "has_missing_required_rules": _truthy(report_map.get("has_missing_required_rules"), default=False),
        "has_segmentation_failure": _truthy(report_map.get("has_segmentation_failure"), default=False),
        "raw_candidate_count": raw_candidate_count,
        "segmented_candidate_count": max(_parse_int(str(report_map.get("segmented_candidate_count", 0))), 0),
        "valid_rule_count": valid_rule_count,
        "invalid_rule_count": invalid_rule_count,
        "dropped_candidate_count": dropped_candidate_count,
        "count_consistent": count_consistent,
        "has_code_extraction": has_code_extraction,
        "code_extraction_sufficient": code_extraction_sufficient,
        "code_candidate_count": code_candidate_count,
        "code_surface_count": code_surface_count,
        "missing_code_surfaces": list(_normalize_reason_codes(report_map.get("missing_code_surfaces"))),
        "has_code_coverage_gap": has_code_coverage_gap,
        "has_code_doc_conflict": has_code_doc_conflict,
        "has_code_token_artifacts": has_code_token_artifacts,
        "has_quality_insufficiency": has_quality_insufficiency,
        "invalid_code_candidate_count": max(_parse_int(str(report_map.get("invalid_code_candidate_count", 0))), 0),
        "code_token_artifact_count": max(_parse_int(str(report_map.get("code_token_artifact_count", 0))), 0),
        "artifact_ratio_exceeded": artifact_ratio_exceeded,
        "artifact_ratio": float(report_map.get("artifact_ratio", 0.0) or 0.0),
    }

    return {
        "Outcome": outcome,
        "ValidationResult": validation_result,
        "ExecutionEvidence": bool(extraction_ran),
        "InventoryLoaded": inventory_loaded,
        "ExtractedCount": extracted_count,
        "ValidRuleCount": valid_rule_count,
        "InvalidRuleCount": invalid_rule_count,
        "DroppedCandidateCount": dropped_candidate_count,
        "ValidationReasonCodes": reason_codes,
        "RenderConsistency": "passed" if render_consistent else "failed",
        "CountConsistency": "passed" if count_consistent else "failed",
        "CodeExtractionRun": has_code_extraction,
        "CodeCoverageSufficient": code_extraction_sufficient,
        "CodeCandidateCount": code_candidate_count,
        "CodeSurfaceCount": code_surface_count,
        "MissingCodeSurfaces": list(_normalize_reason_codes(report_map.get("missing_code_surfaces"))),
        "InventoryFileStatus": inventory_file_status,
        "InventoryFileMode": inventory_file_mode,
        "Inventory": {
            "sha256": inventory_sha256,
            "count": extracted_count,
        },
        "ValidationReport": normalized_report,
        "ReportSha": _build_report_sha(normalized_report),
        "SourcePhase": str(persistence_result.get("source_phase") or "1.5-BusinessRules"),
        "ExtractorVersion": str(persistence_result.get("extractor_version") or "unknown"),
        "ExtractionSource": str(persistence_result.get("extraction_source") or "deterministic"),
    }


def hydrate_business_rules_state_from_artifacts(
    *,
    state: MutableMapping[str, object],
    status_path: Path,
    inventory_path: Path,
) -> bool:
    """Hydrate ``SESSION_STATE.BusinessRules`` from persisted artifacts.

    Returns True when artifact state was applied, otherwise False.
    """

    if not status_path.exists() or not status_path.is_file():
        return False
    try:
        status_text = status_path.read_text(encoding="utf-8")
    except Exception:
        return False

    status_fields = _parse_status_fields(status_text)
    outcome = status_fields.get("outcome", "").strip().lower()
    execution_evidence = _parse_bool(status_fields.get("executionevidence", "false"))
    if not outcome:
        return False
    if outcome not in _RESOLVED_OUTCOMES:
        return False

    inventory_loaded = False
    inventory_rules: list[str] = []
    inventory_sha = "0" * 64
    inventory_report: Any = None
    if inventory_path.exists() and inventory_path.is_file():
        try:
            inventory_text = inventory_path.read_text(encoding="utf-8")
            report = validate_inventory_markdown(inventory_text, expected_rules=outcome == "extracted")
            inventory_report = report
            inventory_rules = [rule.text for rule in report.valid_rules]
            inventory_loaded = bool(report.is_compliant or outcome != "extracted")
            normalized = inventory_text if inventory_text.endswith("\n") else inventory_text + "\n"
            inventory_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except Exception:
            inventory_loaded = False
            inventory_rules = []

    valid_rules = _parse_int(status_fields.get("validrules", "0"), default=0)
    invalid_rules = _parse_int(status_fields.get("invalidrules", "0"), default=0)
    dropped_candidates = _parse_int(status_fields.get("droppedcandidates", "0"), default=0)
    quality_reason_codes = _parse_csv_reasons(status_fields.get("reasoncodes", ""))
    validation_result = status_fields.get("validationresult", "failed").strip().lower()
    if validation_result not in {"passed", "failed"}:
        validation_result = "failed"

    if valid_rules <= 0 and inventory_report is not None:
        valid_rules = int(getattr(inventory_report, "valid_rule_count", 0) or 0)
    if invalid_rules <= 0 and inventory_report is not None:
        invalid_rules = int(getattr(inventory_report, "invalid_rule_count", 0) or 0)
    if dropped_candidates <= 0 and inventory_report is not None:
        dropped_candidates = int(getattr(inventory_report, "dropped_candidate_count", 0) or 0)
    if status_fields.get("validationresult") is None and inventory_report is not None:
        validation_result = "passed" if bool(getattr(inventory_report, "is_compliant", False)) else "failed"
    code_extraction_run = _parse_bool(status_fields.get("codeextractionrun", "false"))
    code_coverage_sufficient = _parse_bool(status_fields.get("codecoveragesufficient", "false"))
    code_candidate_count = _parse_int(status_fields.get("codecandidatecount", "0"), default=0)
    code_surface_count = _parse_int(status_fields.get("codesurfacecount", "0"), default=0)
    missing_code_surfaces = _parse_csv_reasons(status_fields.get("missingcodesurfaces", ""))
    render_consistency = status_fields.get("renderconsistency", "failed").strip().lower()
    count_consistency = status_fields.get("countconsistency", "failed").strip().lower()
    if render_consistency not in {"passed", "failed"}:
        render_consistency = "failed"
    if count_consistency not in {"passed", "failed"}:
        count_consistency = "failed"

    extracted_count = valid_rules if outcome == "extracted" else 0
    if outcome == "extracted" and len(inventory_rules) != extracted_count:
        return False
    if outcome == "extracted" and (not inventory_loaded or extracted_count <= 0):
        return False
    if outcome == "extracted" and validation_result != "passed":
        return False

    if outcome == "extracted" and not execution_evidence:
        return False
    if outcome == "extracted" and code_extraction_run and (not code_coverage_sufficient):
        return False

    report_payload: dict[str, Any] = {
        "is_compliant": validation_result == "passed",
        "has_invalid_rules": invalid_rules > 0,
        "has_render_mismatch": render_consistency == "failed",
        "has_source_violation": "BUSINESS_RULES_SOURCE_VIOLATION" in quality_reason_codes,
        "has_missing_required_rules": "BUSINESS_RULES_MISSING_REQUIRED_RULES" in quality_reason_codes,
        "has_segmentation_failure": "BUSINESS_RULES_SEGMENTATION_FAILED" in quality_reason_codes,
        "raw_candidate_count": _parse_int(status_fields.get("rawcandidatecount", "0"), default=0),
        "segmented_candidate_count": _parse_int(status_fields.get("segmentedcandidatecount", "0"), default=0),
        "valid_rule_count": valid_rules,
        "invalid_rule_count": invalid_rules,
        "dropped_candidate_count": dropped_candidates,
        "count_consistent": count_consistency == "passed",
        "has_code_extraction": code_extraction_run,
        "code_extraction_sufficient": code_coverage_sufficient,
        "code_candidate_count": code_candidate_count,
        "code_surface_count": code_surface_count,
        "missing_code_surfaces": missing_code_surfaces,
        "has_code_coverage_gap": not code_coverage_sufficient,
        "has_code_doc_conflict": "BUSINESS_RULES_CODE_DOC_CONFLICT" in quality_reason_codes,
    }

    scope_obj = state.get("Scope")
    scope = dict(scope_obj) if isinstance(scope_obj, dict) else {}
    canonical_outcome = outcome
    scope["BusinessRules"] = canonical_outcome
    state["Scope"] = scope

    business_obj = state.get("BusinessRules")
    business_rules: dict[str, Any] = dict(business_obj) if isinstance(business_obj, dict) else {}
    business_rules["Outcome"] = canonical_outcome
    business_rules["ValidationResult"] = validation_result
    business_rules["QualityGate"] = "passed" if validation_result == "passed" else "failed"
    business_rules["ExecutionEvidence"] = execution_evidence
    business_rules["InventoryLoaded"] = bool(inventory_loaded)
    business_rules["ExtractedCount"] = extracted_count
    business_rules["ValidRuleCount"] = valid_rules
    business_rules["Inventory"] = {
        "sha256": inventory_sha,
        "count": extracted_count,
    }
    business_rules["InvalidRuleCount"] = invalid_rules
    business_rules["DroppedCandidateCount"] = dropped_candidates
    business_rules["ValidationReasonCodes"] = quality_reason_codes
    business_rules["RenderConsistency"] = render_consistency
    business_rules["CountConsistency"] = count_consistency
    business_rules["ValidationReport"] = report_payload
    business_rules["CodeExtractionRun"] = code_extraction_run
    business_rules["CodeCoverageSufficient"] = code_coverage_sufficient
    business_rules["CodeCandidateCount"] = code_candidate_count
    business_rules["CodeSurfaceCount"] = code_surface_count
    business_rules["MissingCodeSurfaces"] = missing_code_surfaces
    business_rules["ReportSha"] = _build_report_sha(report_payload)
    business_rules["QualityReportVersion"] = "br-quality-v2"
    if inventory_loaded:
        business_rules["InventoryFileStatus"] = "written"
        business_rules["InventoryFileMode"] = "update"
        business_rules["Rules"] = list(inventory_rules)
    state["BusinessRules"] = business_rules
    return True
