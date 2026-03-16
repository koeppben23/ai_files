from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from governance.engine.business_rules_validation import validate_inventory_markdown
from governance.infrastructure.session_pointer import is_session_pointer_document

_CANONICAL_OUTCOMES = {"extracted", "gap-detected", "unresolved"}
_LEGACY_OUTCOMES = {"not-applicable", "deferred", "skipped"}
_ACCEPTED_OUTCOMES = _CANONICAL_OUTCOMES | _LEGACY_OUTCOMES
POINTER_AS_SESSION_STATE_ERROR = "SESSION_STATE_POINTER_PASSED_AS_SESSION_STATE"

_DISCOVERY_OUTCOME_STATUSES = {
    "accepted_for_validation",
    "dropped_technical_artifact",
    "dropped_missing_enforcement_anchor",
    "dropped_missing_business_semantics",
    "dropped_non_business_surface",
    "dropped_schema_only",
    "dropped_non_executable_normative_text",
}


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


def _parse_float(token: object, default: float = 0.0) -> float:
    probe = str(token or "").strip()
    if not probe:
        return default
    try:
        return float(probe)
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


def _aggregate_discovery_outcome_counts(
    discovery_outcomes: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, int]:
    """Aggregate outcome counts from discovery_outcomes list.
    
    This is the SSOT for deriving diagnostic counts from raw discovery outcomes.
    Returns a dict with aggregated counts for each outcome category.
    """
    if not discovery_outcomes:
        return {
            "raw_candidate_count": 0,
            "dropped_candidate_count": 0,
            "dropped_non_business_surface_count": 0,
            "dropped_schema_only_count": 0,
            "dropped_non_executable_normative_text_count": 0,
            "dropped_technical_artifact_count": 0,
            "dropped_missing_enforcement_anchor_count": 0,
            "dropped_missing_business_semantics_count": 0,
            "accepted_for_validation_count": 0,
        }
    
    counts: dict[str, int] = {
        "raw_candidate_count": 0,
        "dropped_candidate_count": 0,
        "dropped_non_business_surface_count": 0,
        "dropped_schema_only_count": 0,
        "dropped_non_executable_normative_text_count": 0,
        "dropped_technical_artifact_count": 0,
        "dropped_missing_enforcement_anchor_count": 0,
        "dropped_missing_business_semantics_count": 0,
        "accepted_for_validation_count": 0,
    }
    
    status_mapping = {
        "dropped_non_business_surface": "dropped_non_business_surface_count",
        "dropped_schema_only": "dropped_schema_only_count",
        "dropped_non_executable_normative_text": "dropped_non_executable_normative_text_count",
        "dropped_technical_artifact": "dropped_technical_artifact_count",
        "dropped_missing_enforcement_anchor": "dropped_missing_enforcement_anchor_count",
        "dropped_missing_business_semantics": "dropped_missing_business_semantics_count",
        "accepted_for_validation": "accepted_for_validation_count",
    }
    
    for outcome in discovery_outcomes:
        if not isinstance(outcome, dict):
            continue
        status = str(outcome.get("status", "")).strip()
        counts["raw_candidate_count"] += 1
        
        if status != "accepted_for_validation":
            counts["dropped_candidate_count"] += 1
        
        count_key = status_mapping.get(status)
        if count_key:
            counts[count_key] += 1
    
    return counts


def _build_report_sha(report: Mapping[str, Any]) -> str:
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CodeExtractionCounters:
    raw_candidate_count: int
    dropped_candidate_count: int
    candidate_count: int
    validated_code_rule_count: int
    invalid_code_candidate_count: int
    # Diagnostic fields for tightened business rule extraction
    dropped_non_business_surface_count: int = 0
    dropped_schema_only_count: int = 0
    dropped_non_executable_normative_text_count: int = 0
    accepted_business_enforcement_count: int = 0
    rejected_non_business_subject_count: int = 0

    def __post_init__(self) -> None:
        # Hard invariant: dropped + candidate must equal raw
        computed_dropped = self.raw_candidate_count - self.candidate_count
        if self.dropped_candidate_count != computed_dropped:
            raise ValueError(
                f"dropped_candidate_count ({self.dropped_candidate_count}) must equal "
                f"raw_candidate_count ({self.raw_candidate_count}) - candidate_count ({self.candidate_count}) = {computed_dropped}"
            )
        # Hard invariant: validated + invalid must equal candidate
        computed_validated = self.candidate_count - self.invalid_code_candidate_count
        if self.validated_code_rule_count != computed_validated:
            raise ValueError(
                f"validated_code_rule_count ({self.validated_code_rule_count}) must equal "
                f"candidate_count ({self.candidate_count}) - invalid_code_candidate_count ({self.invalid_code_candidate_count}) = {computed_validated}"
            )

    def to_report_fields(self) -> dict[str, int]:
        return {
            "raw_candidate_count": self.raw_candidate_count,
            "dropped_candidate_count": self.dropped_candidate_count,
            "candidate_count": self.candidate_count,
            "code_candidate_count": self.candidate_count,
            "validated_code_rule_count": self.validated_code_rule_count,
            "code_valid_rule_count": self.validated_code_rule_count,
            "invalid_code_candidate_count": self.invalid_code_candidate_count,
            # Diagnostic fields for tightened business rule extraction
            "dropped_non_business_surface_count": self.dropped_non_business_surface_count,
            "dropped_schema_only_count": self.dropped_schema_only_count,
            "dropped_non_executable_normative_text_count": self.dropped_non_executable_normative_text_count,
            "accepted_business_enforcement_count": self.accepted_business_enforcement_count,
            "rejected_non_business_subject_count": self.rejected_non_business_subject_count,
        }


def _build_code_extraction_counters(report_map: Mapping[str, Any]) -> CodeExtractionCounters:
    candidate_count_keys = ("candidate_count", "code_candidate_count")
    validated_count_keys = ("validated_code_rule_count", "code_valid_rule_count")

    outcome_counts = _aggregate_discovery_outcome_counts(
        report_map.get("discovery_outcomes") or []
    )

    candidate_count_provided = any(key in report_map for key in candidate_count_keys)
    validated_code_rule_count_provided = any(key in report_map for key in validated_count_keys)
    invalid_code_candidate_count_provided = "invalid_code_candidate_count" in report_map
    dropped_candidate_count_provided = "dropped_candidate_count" in report_map
    raw_candidate_count_provided = "raw_candidate_count" in report_map

    candidate_count = max(
        _parse_int(
            str(report_map.get("candidate_count", report_map.get("code_candidate_count", 0))),
            default=0,
        ),
        0,
    )
    validated_code_rule_count = max(
        _parse_int(
            str(
                report_map.get(
                    "validated_code_rule_count",
                    report_map.get("code_valid_rule_count", 0),
                )
            ),
            default=0,
        ),
        0,
    )
    invalid_code_candidate_count = max(
        _parse_int(str(report_map.get("invalid_code_candidate_count", 0)), default=0),
        0,
    )

    if candidate_count_provided and candidate_count > 0 and (validated_code_rule_count + invalid_code_candidate_count) == 0:
        validated_code_rule_count = min(
            candidate_count,
            max(_parse_int(str(report_map.get("valid_rule_count", 0)), default=0), 0),
        )
        invalid_code_candidate_count = max(candidate_count - validated_code_rule_count, 0)
    elif candidate_count_provided and not validated_code_rule_count_provided and not invalid_code_candidate_count_provided:
        validated_code_rule_count = min(
            candidate_count,
            max(_parse_int(str(report_map.get("valid_rule_count", 0)), default=0), 0),
        )
        invalid_code_candidate_count = max(candidate_count - validated_code_rule_count, 0)
    elif candidate_count_provided and validated_code_rule_count_provided and not invalid_code_candidate_count_provided:
        invalid_code_candidate_count = max(candidate_count - validated_code_rule_count, 0)
    elif candidate_count_provided and invalid_code_candidate_count_provided and not validated_code_rule_count_provided:
        validated_code_rule_count = max(candidate_count - invalid_code_candidate_count, 0)
    elif not candidate_count_provided:
        candidate_count = validated_code_rule_count + invalid_code_candidate_count

    if candidate_count != validated_code_rule_count + invalid_code_candidate_count:
        candidate_count = validated_code_rule_count + invalid_code_candidate_count

    # Use aggregated outcome counts as primary source when discovery_outcomes is present
    # Explicit report_map values take precedence for backward compatibility
    has_discovery_outcomes = bool(report_map.get("discovery_outcomes"))
    
    dropped_candidate_count = max(
        _parse_int(str(report_map.get("dropped_candidate_count", outcome_counts.get("dropped_candidate_count", 0)))), 0
    )
    raw_candidate_count = max(
        _parse_int(str(report_map.get("raw_candidate_count", outcome_counts.get("raw_candidate_count", 0)))),
        0,
    )
    
    # When discovery_outcomes is provided, use aggregated counts as SSOT
    if has_discovery_outcomes and outcome_counts.get("raw_candidate_count", 0) > 0:
        raw_candidate_count = outcome_counts.get("raw_candidate_count", raw_candidate_count)
        dropped_candidate_count = outcome_counts.get("dropped_candidate_count", dropped_candidate_count)
        # candidate_count is derived from accepted_for_validation
        if outcome_counts.get("accepted_for_validation_count", 0) > 0:
            candidate_count = outcome_counts.get("accepted_for_validation_count", candidate_count)
    elif not has_discovery_outcomes:
        # Backward compatibility: reconcile inconsistent counts when no discovery_outcomes
        if raw_candidate_count != dropped_candidate_count + candidate_count:
            raw_candidate_count = dropped_candidate_count + candidate_count
    
    # Diagnostic fields for tightened business rule extraction
    # When discovery_outcomes is present, use aggregated counts as SSOT (hard precedence)
    # report_map values only used as fallback when no discovery_outcomes
    if has_discovery_outcomes and outcome_counts.get("raw_candidate_count", 0) > 0:
        # SSOT: aggregated outcome counts take hard precedence
        dropped_non_business_surface_count = outcome_counts.get("dropped_non_business_surface_count", 0)
        dropped_schema_only_count = outcome_counts.get("dropped_schema_only_count", 0)
        dropped_non_executable_normative_text_count = outcome_counts.get("dropped_non_executable_normative_text_count", 0)
        accepted_business_enforcement_count = outcome_counts.get("accepted_for_validation_count", 0)
    else:
        # Fallback to report_map values when no discovery_outcomes
        dropped_non_business_surface_count = max(
            _parse_int(str(report_map.get("dropped_non_business_surface_count", 0))), 0
        )
        dropped_schema_only_count = max(
            _parse_int(str(report_map.get("dropped_schema_only_count", 0))), 0
        )
        dropped_non_executable_normative_text_count = max(
            _parse_int(str(report_map.get("dropped_non_executable_normative_text_count", 0))), 0
        )
        accepted_business_enforcement_count = max(
            _parse_int(str(report_map.get("accepted_business_enforcement_count", 0))), 0
        )
    
    # rejected_non_business_subject_count comes from validation, not discovery
    # It tracks code candidates rejected during validation phase
    rejected_non_business_subject_count = max(_parse_int(str(report_map.get("rejected_non_business_subject_count", 0))), 0)

    # SSOT invariant validation: when discovery_outcomes present, reconcile all counts
    if has_discovery_outcomes and outcome_counts.get("raw_candidate_count", 0) > 0:
        # The aggregated counts take precedence - reconcile all related values
        raw_candidate_count = outcome_counts.get("raw_candidate_count", raw_candidate_count)
        dropped_candidate_count = outcome_counts.get("dropped_candidate_count", dropped_candidate_count)
        candidate_count = outcome_counts.get("accepted_for_validation_count", candidate_count)
        
        # When using aggregated outcomes, assume all candidates are initially valid
        # (validation phase determines actual validity later)
        if validated_code_rule_count_provided:
            # Keep explicit validated count if provided
            pass
        else:
            # Default: all discovered candidates are valid until validation proves otherwise
            validated_code_rule_count = candidate_count
            invalid_code_candidate_count = 0

    return CodeExtractionCounters(
        raw_candidate_count=raw_candidate_count,
        dropped_candidate_count=dropped_candidate_count,
        candidate_count=candidate_count,
        validated_code_rule_count=validated_code_rule_count,
        invalid_code_candidate_count=invalid_code_candidate_count,
        dropped_non_business_surface_count=dropped_non_business_surface_count,
        dropped_schema_only_count=dropped_schema_only_count,
        dropped_non_executable_normative_text_count=dropped_non_executable_normative_text_count,
        accepted_business_enforcement_count=accepted_business_enforcement_count,
        rejected_non_business_subject_count=rejected_non_business_subject_count,
    )


def _build_code_extraction_report(
    *,
    report_map: Mapping[str, Any],
    counters: CodeExtractionCounters,
    report_sha: str,
) -> dict[str, Any]:
    valid_rule_ratio = _parse_float(report_map.get("valid_rule_ratio"), default=0.0)
    if valid_rule_ratio <= 0.0 and counters.candidate_count > 0:
        valid_rule_ratio = counters.validated_code_rule_count / counters.candidate_count

    artifact_ratio = _parse_float(report_map.get("artifact_ratio"), default=0.0)
    code_token_artifact_count = max(_parse_int(str(report_map.get("code_token_artifact_count", 0))), 0)
    if artifact_ratio <= 0.0 and counters.candidate_count > 0:
        artifact_ratio = code_token_artifact_count / counters.candidate_count

    return {
        "scanned_file_count": max(
            _parse_int(
                str(
                    report_map.get(
                        "scanned_file_count",
                        report_map.get("code_surface_count", 0),
                    )
                )
            ),
            0,
        ),
        **counters.to_report_fields(),
        "code_token_artifact_count": code_token_artifact_count,
        "valid_rule_ratio": max(valid_rule_ratio, 0.0),
        "artifact_ratio": max(artifact_ratio, 0.0),
        "coverage_quality_grade": str(report_map.get("coverage_quality_grade", "unknown") or "unknown"),
        "missing_expected_surfaces": list(_normalize_reason_codes(report_map.get("missing_code_surfaces"))),
        "reason_codes": list(_normalize_reason_codes(report_map.get("reason_codes"))),
        "is_sufficient": _truthy(report_map.get("code_extraction_sufficient"), default=False),
        "semantic_type_distribution": dict(report_map.get("semantic_type_distribution") or {}),
        "surface_type_distribution": dict(report_map.get("surface_type_distribution") or {}),
        "surface_balance_score": _parse_float(report_map.get("surface_balance_score"), default=0.0),
        "semantic_diversity_score": _parse_float(report_map.get("semantic_diversity_score"), default=0.0),
        "quality_insufficiency_reasons": _normalize_reason_codes(report_map.get("quality_insufficiency_reasons")),
        "template_overfit_count": max(_parse_int(str(report_map.get("template_overfit_count", 0))), 0),
        "scanned_surfaces": list(report_map.get("scanned_surfaces") or []),
        "discovery_outcomes": list(report_map.get("discovery_outcomes") or []),
        "report_sha": report_sha,
    }


def has_br_signal(
    *,
    declared_outcome: str = "",
    report: Mapping[str, Any] | None = None,
    persistence_result: Mapping[str, Any] | None = None,
) -> bool:
    """Return True when any Business Rules processing/materialization signal exists."""

    declared = str(declared_outcome or "").strip().lower()
    if declared in {"extracted", "gap-detected"}:
        return True

    report_map = dict(report) if isinstance(report, Mapping) else {}
    if report_map:
        if any(
            key in report_map
            for key in (
                "is_compliant",
                "valid_rule_count",
                "invalid_rule_count",
                "dropped_candidate_count",
                "reason_codes",
                "has_code_extraction",
                "code_extraction_sufficient",
            )
        ):
            return True

    persist = dict(persistence_result) if isinstance(persistence_result, Mapping) else {}
    if _truthy(persist.get("execution_evidence"), default=False):
        return True
    if _truthy(persist.get("extraction_ran"), default=False):
        return True
    if _truthy(persist.get("inventory_loaded"), default=False):
        return True
    if _truthy(persist.get("status_file_present"), default=False):
        return True
    if _truthy(persist.get("inventory_exists"), default=False):
        return True
    if _truthy(persist.get("validation_signal"), default=False):
        return True
    if _truthy(persist.get("report_sha_present"), default=False):
        return True
    if str(persist.get("source_phase") or "").strip().lower() == "1.5-businessrules":
        return True

    extracted_count = _parse_int(str(persist.get("extracted_count", 0)), default=0)
    if extracted_count > 0:
        return True

    return False


def canonicalize_business_rules_outcome(
    *,
    declared_outcome: str,
    extracted_allowed: bool,
    final_report_available: bool,
    br_signal: bool,
) -> str:
    """Resolve canonical business-rules outcome to exactly three states."""

    if extracted_allowed:
        return "extracted"
    if final_report_available:
        return "gap-detected"
    if br_signal:
        return "gap-detected"
    _ = declared_outcome
    return "unresolved"


def build_business_rules_state_snapshot(
    *,
    report: Mapping[str, Any],
    persistence_result: Mapping[str, Any],
    code_extraction_report: Mapping[str, Any] | None = None,
    compute_report_sha: bool = True,
) -> dict[str, Any]:
    """Build the canonical BusinessRules state snapshot (SSOT).

    This snapshot is the single source for both SESSION_STATE.BusinessRules and
    business-rules-status.md rendering.
    """

    report_map = dict(report)
    if isinstance(code_extraction_report, Mapping):
        for key, value in dict(code_extraction_report).items():
            report_map.setdefault(str(key), value)

    counters = _build_code_extraction_counters(report_map)
    valid_rule_count = max(_parse_int(str(report_map.get("valid_rule_count", 0))), 0)
    invalid_rule_count = max(_parse_int(str(report_map.get("invalid_rule_count", 0))), 0)
    dropped_candidate_count = counters.dropped_candidate_count
    raw_candidate_count = counters.raw_candidate_count
    code_candidate_count = counters.candidate_count
    code_surface_count = max(
        _parse_int(str(report_map.get("code_surface_count", report_map.get("scanned_file_count", 0)))),
        0,
    )
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
    has_source_violation = _truthy(report_map.get("has_source_violation"), default=False)
    has_segmentation_failure = _truthy(report_map.get("has_segmentation_failure"), default=False)
    report_is_compliant = _truthy(report_map.get("is_compliant"), default=False)
    reason_codes = sorted(set(_normalize_reason_codes(report_map.get("reason_codes"))))
    inventory_written = _truthy(persistence_result.get("inventory_written"), default=True)
    declared_outcome = str(persistence_result.get("declared_outcome") or "").strip().lower()
    report_finalized = _truthy(
        persistence_result.get("report_finalized"),
        default=any(
            key in report_map
            for key in (
                "is_compliant",
                "valid_rule_count",
                "invalid_rule_count",
                "dropped_candidate_count",
                "count_consistent",
            )
        ),
    )

    severe_quality_failure = (
        has_render_mismatch
        or has_source_violation
        or has_segmentation_failure
        or (not count_consistent)
        or (not render_consistent)
    )
    if severe_quality_failure:
        has_quality_insufficiency = True
        code_extraction_sufficient = False
        has_code_coverage_gap = True
        if "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT" not in reason_codes:
            reason_codes.append("BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT")
            reason_codes = sorted(set(reason_codes))

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
    br_signal = has_br_signal(
        declared_outcome=declared_outcome,
        report=report_map,
        persistence_result={
            **dict(persistence_result),
            "extraction_ran": extraction_ran,
            "inventory_loaded": _truthy(persistence_result.get("inventory_loaded"), default=False),
            "execution_evidence": _truthy(persistence_result.get("execution_evidence"), default=extraction_ran),
            "extracted_count": valid_rule_count,
        },
    )
    outcome = canonicalize_business_rules_outcome(
        declared_outcome=declared_outcome,
        extracted_allowed=extracted_allowed,
        final_report_available=report_finalized,
        br_signal=br_signal,
    )

    inventory_file_status = str(persistence_result.get("inventory_file_status") or "unknown").strip() or "unknown"
    inventory_file_mode = str(persistence_result.get("inventory_file_mode") or "unknown").strip() or "unknown"
    inventory_sha256 = str(persistence_result.get("inventory_sha256") or "").strip() or ("0" * 64)
    inventory_loaded = bool(outcome == "extracted" and inventory_file_status == "written")
    extracted_count = valid_rule_count if outcome == "extracted" else 0
    validation_result = "passed" if extracted_allowed else "failed"
    coverage_quality_grade = str(report_map.get("coverage_quality_grade", "unknown") or "unknown")
    surface_balance_score = _parse_float(report_map.get("surface_balance_score"), default=0.0)
    semantic_diversity_score = _parse_float(report_map.get("semantic_diversity_score"), default=0.0)
    quality_insufficiency_reasons = _normalize_reason_codes(report_map.get("quality_insufficiency_reasons"))
    code_token_artifact_count = max(_parse_int(str(report_map.get("code_token_artifact_count", 0))), 0)
    template_overfit_count = max(_parse_int(str(report_map.get("template_overfit_count", 0))), 0)

    normalized_report: dict[str, Any] = {
        "is_compliant": report_is_compliant,
        "has_invalid_rules": has_invalid_rules,
        "has_render_mismatch": has_render_mismatch,
        "has_source_violation": has_source_violation,
        "has_missing_required_rules": _truthy(report_map.get("has_missing_required_rules"), default=False),
        "has_segmentation_failure": has_segmentation_failure,
        "segmented_candidate_count": max(_parse_int(str(report_map.get("segmented_candidate_count", 0))), 0),
        "valid_rule_count": valid_rule_count,
        "invalid_rule_count": invalid_rule_count,
        "count_consistent": count_consistent,
        "has_code_extraction": has_code_extraction,
        "code_extraction_sufficient": code_extraction_sufficient,
        "code_surface_count": code_surface_count,
        "missing_code_surfaces": list(
            _normalize_reason_codes(
                report_map.get("missing_code_surfaces", report_map.get("missing_expected_surfaces"))
            )
        ),
        "has_code_coverage_gap": has_code_coverage_gap,
        "has_code_doc_conflict": has_code_doc_conflict,
        "has_code_token_artifacts": has_code_token_artifacts,
        "has_quality_insufficiency": has_quality_insufficiency,
        **counters.to_report_fields(),
        "code_token_artifact_count": code_token_artifact_count,
        "artifact_ratio_exceeded": artifact_ratio_exceeded,
        "artifact_ratio": _parse_float(report_map.get("artifact_ratio"), default=0.0),
        "template_overfit_count": template_overfit_count,
        "surface_balance_score": surface_balance_score,
        "semantic_diversity_score": semantic_diversity_score,
        "quality_insufficiency_reasons": quality_insufficiency_reasons,
        "coverage_quality_grade": coverage_quality_grade,
    }
    report_sha = _build_report_sha(normalized_report) if compute_report_sha else str(persistence_result.get("report_sha") or "")
    final_code_extraction_report = _build_code_extraction_report(
        report_map=report_map,
        counters=counters,
        report_sha=report_sha,
    )

    return {
        "Outcome": outcome,
        "ValidationResult": validation_result,
        "HasSignal": br_signal,
        "ExecutionEvidence": bool(extraction_ran),
        "InventoryLoaded": inventory_loaded,
        "ExtractedCount": extracted_count,
        "ValidRuleCount": valid_rule_count,
        "InvalidRuleCount": invalid_rule_count,
        "DroppedCandidateCount": dropped_candidate_count,
        "RawCandidateCount": raw_candidate_count,
        "CandidateCount": counters.candidate_count,
        "ValidationReasonCodes": reason_codes,
        "RenderConsistency": "passed" if render_consistent else "failed",
        "CountConsistency": "passed" if count_consistent else "failed",
        "CodeExtractionRun": has_code_extraction,
        "CodeCoverageSufficient": code_extraction_sufficient,
        "CodeCandidateCount": code_candidate_count,
        "ValidatedCodeRuleCount": counters.validated_code_rule_count,
        "InvalidCodeCandidateCount": counters.invalid_code_candidate_count,
        "CodeSurfaceCount": code_surface_count,
        "MissingCodeSurfaces": list(
            _normalize_reason_codes(
                report_map.get("missing_code_surfaces", report_map.get("missing_expected_surfaces"))
            )
        ),
        "CoverageQualityGrade": coverage_quality_grade,
        "SurfaceBalanceScore": surface_balance_score,
        "SemanticDiversityScore": semantic_diversity_score,
        "QualityInsufficiencyReasons": quality_insufficiency_reasons,
        "CodeTokenArtifactCount": code_token_artifact_count,
        "TemplateOverfitCount": template_overfit_count,
        "InventoryFileStatus": inventory_file_status,
        "InventoryFileMode": inventory_file_mode,
        "Inventory": {
            "sha256": inventory_sha256,
            "count": extracted_count,
        },
        "ValidationReport": normalized_report,
        "CodeExtractionReport": final_code_extraction_report,
        "ReportSha": report_sha,
        "SourcePhase": str(persistence_result.get("source_phase") or "1.5-BusinessRules"),
        "ExtractorVersion": str(persistence_result.get("extractor_version") or "unknown"),
        "ExtractionSource": str(persistence_result.get("extraction_source") or "deterministic"),
    }


def build_business_rules_code_extraction_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    report = snapshot.get("CodeExtractionReport")
    if isinstance(report, Mapping):
        return dict(report)

    validation_report = snapshot.get("ValidationReport")
    report_map = dict(validation_report) if isinstance(validation_report, Mapping) else {}
    counters = _build_code_extraction_counters(report_map)
    return _build_code_extraction_report(
        report_map=report_map,
        counters=counters,
        report_sha=str(snapshot.get("ReportSha") or ""),
    )


def hydrate_business_rules_state_from_artifacts(
    *,
    state: MutableMapping[str, object],
    status_path: Path,
    inventory_path: Path,
) -> bool:
    """Hydrate ``SESSION_STATE.BusinessRules`` from persisted artifacts.

    Returns True when artifact state was applied, otherwise False.
    """

    if is_session_pointer_document(state):
        raise ValueError(POINTER_AS_SESSION_STATE_ERROR)

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
    if outcome not in _ACCEPTED_OUTCOMES:
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
    code_extraction_run = _parse_bool(status_fields.get("codeextractionrun", "true"))
    code_coverage_sufficient = _parse_bool(status_fields.get("codecoveragesufficient", "true"))
    raw_candidate_count = _parse_int(status_fields.get("rawcandidatecount", "0"), default=0)
    code_candidate_count = _parse_int(status_fields.get("codecandidatecount", "0"), default=0)
    candidate_count = _parse_int(status_fields.get("candidatecount", str(code_candidate_count)), default=code_candidate_count)
    validated_code_rule_count = _parse_int(status_fields.get("validatedcoderulecount", "0"), default=0)
    invalid_code_candidate_count = _parse_int(status_fields.get("invalidcodecandidatecount", "0"), default=0)
    code_token_artifact_count = _parse_int(status_fields.get("codetokenartifactcount", "0"), default=0)
    template_overfit_count = _parse_int(status_fields.get("templateoverfitcount", "0"), default=0)
    code_surface_count = _parse_int(status_fields.get("codesurfacecount", "0"), default=0)
    missing_code_surfaces = _parse_csv_reasons(status_fields.get("missingcodesurfaces", ""))
    coverage_quality_grade = status_fields.get("coveragequalitygrade", "unknown").strip() or "unknown"
    surface_balance_score = _parse_float(status_fields.get("surfacebalancescore", "0.0"), default=0.0)
    semantic_diversity_score = _parse_float(status_fields.get("semanticdiversityscore", "0.0"), default=0.0)
    quality_insufficiency_reasons = _parse_csv_reasons(status_fields.get("qualityinsufficiencyreasons", ""))
    render_consistency = status_fields.get("renderconsistency", "").strip().lower()
    count_consistency = status_fields.get("countconsistency", "").strip().lower()
    if not render_consistency and inventory_report is not None:
        render_consistency = "passed" if not bool(getattr(inventory_report, "has_render_mismatch", False)) else "failed"
    if not count_consistency and inventory_report is not None:
        count_consistency = "passed" if bool(getattr(inventory_report, "count_consistent", True)) else "failed"
    if render_consistency not in {"passed", "failed"}:
        render_consistency = "failed"
    if count_consistency not in {"passed", "failed"}:
        count_consistency = "failed"

    extracted_count = valid_rules if outcome == "extracted" else 0
    if outcome == "extracted" and len(inventory_rules) != extracted_count:
        count_consistency = "failed"
        validation_result = "failed"
    if outcome == "extracted" and (not inventory_loaded or extracted_count <= 0):
        validation_result = "failed"
    if outcome == "extracted" and not execution_evidence:
        validation_result = "failed"
    if outcome == "extracted" and code_extraction_run and (not code_coverage_sufficient):
        validation_result = "failed"
    if outcome == "extracted" and render_consistency == "failed":
        validation_result = "failed"

    report_payload: dict[str, Any] = {
        "is_compliant": validation_result == "passed",
        "has_invalid_rules": invalid_rules > 0,
        "has_render_mismatch": render_consistency == "failed",
        "has_source_violation": "BUSINESS_RULES_SOURCE_VIOLATION" in quality_reason_codes,
        "has_missing_required_rules": "BUSINESS_RULES_MISSING_REQUIRED_RULES" in quality_reason_codes,
        "has_segmentation_failure": "BUSINESS_RULES_SEGMENTATION_FAILED" in quality_reason_codes,
        "raw_candidate_count": raw_candidate_count,
        "segmented_candidate_count": _parse_int(status_fields.get("segmentedcandidatecount", "0"), default=0),
        "valid_rule_count": valid_rules,
        "invalid_rule_count": invalid_rules,
        "dropped_candidate_count": dropped_candidates,
        "count_consistent": count_consistency == "passed",
        "has_code_extraction": code_extraction_run,
        "code_extraction_sufficient": code_coverage_sufficient,
        "candidate_count": candidate_count,
        "code_candidate_count": code_candidate_count,
        "validated_code_rule_count": validated_code_rule_count,
        "invalid_code_candidate_count": invalid_code_candidate_count,
        "code_token_artifact_count": code_token_artifact_count,
        "template_overfit_count": template_overfit_count,
        "code_surface_count": code_surface_count,
        "missing_code_surfaces": missing_code_surfaces,
        "has_code_coverage_gap": not code_coverage_sufficient,
        "has_code_doc_conflict": "BUSINESS_RULES_CODE_DOC_CONFLICT" in quality_reason_codes,
        "coverage_quality_grade": coverage_quality_grade,
        "surface_balance_score": surface_balance_score,
        "semantic_diversity_score": semantic_diversity_score,
        "quality_insufficiency_reasons": quality_insufficiency_reasons,
        "reason_codes": quality_reason_codes,
    }

    snapshot = build_business_rules_state_snapshot(
        report=report_payload,
        persistence_result={
            "declared_outcome": outcome,
            "source_phase": status_fields.get("sourcephase", "1.5-BusinessRules"),
            "extractor_version": status_fields.get("extractorversion", "unknown"),
            "extraction_source": status_fields.get("extractionsource", "deterministic"),
            "extraction_ran": code_extraction_run or execution_evidence,
            "execution_evidence": execution_evidence,
            "inventory_loaded": inventory_loaded,
            "inventory_exists": inventory_path.exists() and inventory_path.is_file(),
            "status_file_present": True,
            "validation_signal": bool(status_fields.get("validationresult", "").strip()),
            "report_sha_present": bool(status_fields.get("reportsha", "").strip()),
            "inventory_written": inventory_loaded,
            "inventory_file_status": "written" if inventory_loaded else "withheld",
            "inventory_file_mode": "update" if inventory_loaded else "unknown",
            "inventory_sha256": inventory_sha,
            "report_finalized": bool(status_fields.get("validationresult", "").strip()) or inventory_report is not None,
            "report_sha": status_fields.get("reportsha", "").strip(),
        },
        compute_report_sha=not bool(status_fields.get("reportsha", "").strip()),
    )

    scope_obj = state.get("Scope")
    scope = dict(scope_obj) if isinstance(scope_obj, dict) else {}
    canonical_outcome = str(snapshot.get("Outcome") or "unresolved")
    scope["BusinessRules"] = canonical_outcome
    state["Scope"] = scope

    business_obj = state.get("BusinessRules")
    business_rules: dict[str, Any] = dict(business_obj) if isinstance(business_obj, dict) else {}
    business_rules.update(snapshot)
    business_rules["ValidationResult"] = str(snapshot.get("ValidationResult") or validation_result)
    business_rules["QualityGate"] = "passed" if business_rules.get("ValidationResult") == "passed" else "failed"
    business_rules["QualityReportVersion"] = "br-quality-v2"
    if snapshot.get("Outcome") == "extracted" and inventory_loaded:
        business_rules["InventoryFileStatus"] = "written"
        business_rules["InventoryFileMode"] = "update"
        business_rules["Rules"] = list(inventory_rules)
    state["BusinessRules"] = business_rules
    return True
