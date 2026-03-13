from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, MutableMapping

from governance.engine.business_rules_validation import validate_inventory_markdown

_RESOLVED_OUTCOMES = {"extracted", "not-applicable", "deferred", "skipped"}


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

    inventory_loaded = False
    inventory_rules: list[str] = []
    invalid_rules = 0
    dropped_candidates = 0
    quality_reason_codes: list[str] = []
    quality_gate = "unknown"
    render_consistency = "unknown"
    count_consistency = "unknown"
    source_violations = 0
    segmentation_failures = 0
    validation_report: dict[str, Any] = {}
    inventory_sha = "0" * 64
    if inventory_path.exists() and inventory_path.is_file():
        try:
            inventory_text = inventory_path.read_text(encoding="utf-8")
            inventory_loaded = True
            report = validate_inventory_markdown(inventory_text, expected_rules=outcome == "extracted")
            inventory_rules = [rule.text for rule in report.valid_rules]
            invalid_rules = report.invalid_rule_count
            dropped_candidates = report.dropped_candidate_count
            quality_reason_codes = list(report.reason_codes)
            quality_gate = "passed" if report.is_compliant else "failed"
            render_consistency = "passed" if not report.has_render_mismatch else "failed"
            count_consistency = "passed" if report.count_consistent else "failed"
            source_violations = sum(
                1 for row in report.dropped_candidates if row.reason_code == "BUSINESS_RULES_SOURCE_VIOLATION"
            )
            segmentation_failures = sum(
                1 for row in report.dropped_candidates if row.reason_code == "BUSINESS_RULES_SEGMENTATION_FAILED"
            )
            validation_report = {
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
            }
            normalized = inventory_text if inventory_text.endswith("\n") else inventory_text + "\n"
            inventory_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except Exception:
            inventory_loaded = False
            inventory_rules = []

    extracted_count = len(inventory_rules)

    if not quality_reason_codes and status_fields.get("reasoncodes"):
        quality_reason_codes = _parse_csv_reasons(status_fields.get("reasoncodes", ""))
    if status_fields.get("validationresult") in {"passed", "failed"}:
        quality_gate = status_fields["validationresult"]
    code_extraction_run = _parse_bool(status_fields.get("codeextractionrun", "true"))
    code_coverage_sufficient = _parse_bool(status_fields.get("codecoveragesufficient", "true"))
    code_candidate_count = _parse_int(status_fields.get("codecandidatecount", "0"), default=0)
    code_surface_count = _parse_int(status_fields.get("codesurfacecount", "0"), default=0)
    missing_code_surfaces = _parse_csv_reasons(status_fields.get("missingcodesurfaces", ""))

    if validation_report:
        validation_report["has_code_extraction"] = code_extraction_run
        validation_report["code_extraction_sufficient"] = code_coverage_sufficient
        validation_report["code_candidate_count"] = code_candidate_count
        validation_report["code_surface_count"] = code_surface_count
        validation_report["missing_code_surfaces"] = missing_code_surfaces
        validation_report["has_code_coverage_gap"] = (not code_coverage_sufficient)

    report_is_compliant = bool(validation_report.get("is_compliant") is True)
    has_quality_failure = (
        quality_gate == "failed"
        or invalid_rules > 0
        or dropped_candidates > 0
        or render_consistency == "failed"
        or count_consistency == "failed"
        or (quality_reason_codes and quality_reason_codes != ["none"])
        or (validation_report and not report_is_compliant)
        or (not code_extraction_run)
        or (not code_coverage_sufficient)
    )

    if outcome == "extracted" and (
        not execution_evidence
        or not inventory_loaded
        or extracted_count <= 0
        or has_quality_failure
    ):
        return False

    scope_obj = state.get("Scope")
    scope = dict(scope_obj) if isinstance(scope_obj, dict) else {}
    if outcome in _RESOLVED_OUTCOMES:
        scope["BusinessRules"] = outcome
    state["Scope"] = scope

    business_obj = state.get("BusinessRules")
    business_rules: dict[str, Any] = dict(business_obj) if isinstance(business_obj, dict) else {}
    business_rules["Outcome"] = outcome
    business_rules["ExecutionEvidence"] = execution_evidence
    business_rules["InventoryLoaded"] = bool(inventory_loaded)
    business_rules["ExtractedCount"] = extracted_count
    business_rules["Inventory"] = {
        "sha256": inventory_sha,
        "count": extracted_count,
    }
    business_rules["QualityGate"] = quality_gate
    business_rules["InvalidRuleCount"] = invalid_rules
    business_rules["DroppedCandidateCount"] = dropped_candidates
    business_rules["ValidationReasonCodes"] = quality_reason_codes
    business_rules["RenderConsistency"] = render_consistency
    business_rules["CountConsistency"] = count_consistency
    business_rules["SourceViolationCount"] = source_violations
    business_rules["SegmentationFailureCount"] = segmentation_failures
    business_rules["ValidationReport"] = validation_report
    business_rules["CodeExtractionRun"] = code_extraction_run
    business_rules["CodeCoverageSufficient"] = code_coverage_sufficient
    business_rules["CodeCandidateCount"] = code_candidate_count
    business_rules["CodeSurfaceCount"] = code_surface_count
    business_rules["MissingCodeSurfaces"] = missing_code_surfaces
    business_rules["QualityReportVersion"] = "br-quality-v2"
    if inventory_loaded:
        business_rules["InventoryFileStatus"] = "written"
        business_rules["InventoryFileMode"] = "update"
        business_rules["Rules"] = list(inventory_rules)
    state["BusinessRules"] = business_rules
    return True
