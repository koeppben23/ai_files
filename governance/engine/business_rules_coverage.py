from __future__ import annotations

from dataclasses import dataclass

from governance.engine.business_rules_code_extraction import CodeSurface


RC_CODE_EXTRACTION_NOT_RUN = "BUSINESS_RULES_CODE_EXTRACTION_NOT_RUN"
RC_CODE_COVERAGE_INSUFFICIENT = "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT"
RC_CODE_PROVENANCE_MISSING = "BUSINESS_RULES_CODE_PROVENANCE_MISSING"
RC_CODE_QUALITY_INSUFFICIENT = "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT"


@dataclass(frozen=True)
class CodeExtractionCoverage:
    scanned_surfaces: tuple[CodeSurface, ...]
    scanned_file_count: int
    candidate_count: int
    missing_expected_surfaces: tuple[str, ...]
    reason_codes: tuple[str, ...]
    is_sufficient: bool
    raw_candidate_count: int = 0
    validated_code_rule_count: int = 0
    invalid_code_candidate_count: int = 0
    code_token_artifact_count: int = 0
    valid_rule_ratio: float = 0.0
    artifact_ratio: float = 0.0
    coverage_quality_grade: str = "unknown"
    semantic_type_distribution: dict[str, int] | None = None
    surface_type_distribution: dict[str, int] | None = None


def evaluate_code_extraction_coverage(
    *,
    scanned_surfaces: list[CodeSurface],
    candidate_count: int,
    extraction_ran: bool,
    has_provenance_gaps: bool = False,
    validated_code_rule_count: int = 0,
    invalid_code_candidate_count: int = 0,
    code_token_artifact_count: int = 0,
    semantic_type_distribution: dict[str, int] | None = None,
) -> CodeExtractionCoverage:
    reasons: list[str] = []
    if not extraction_ran:
        reasons.append(RC_CODE_EXTRACTION_NOT_RUN)

    scanned_file_count = len(scanned_surfaces)
    missing_expected_surfaces: list[str] = []

    if scanned_file_count > 0 and candidate_count <= 0:
        reasons.append(RC_CODE_COVERAGE_INSUFFICIENT)

    # Expectation model: track strong domain-oriented surfaces.
    present_types = {surface.surface_type for surface in scanned_surfaces}
    expected_types = {"validator", "permissions", "workflow"}
    for expected in ("validator", "permissions", "workflow"):
        if expected not in present_types and scanned_file_count > 0:
            missing_expected_surfaces.append(expected)

    # Fail-closed in sensible coverage scenarios:
    # - If repo is non-trivial (>= 8 scanned code/config files), missing strong
    #   surfaces is a blocker.
    # - If at least one strong surface exists but others are missing, treat as
    #   partial-coverage gap and block.
    present_expected = len(present_types & expected_types)
    if missing_expected_surfaces and (
        scanned_file_count >= 8
        or present_expected >= 1
    ):
        reasons.append(RC_CODE_COVERAGE_INSUFFICIENT)

    if has_provenance_gaps:
        reasons.append(RC_CODE_PROVENANCE_MISSING)

    raw_candidate_count = max(candidate_count, 0)
    valid_rule_ratio = (validated_code_rule_count / raw_candidate_count) if raw_candidate_count > 0 else 0.0
    artifact_ratio = (code_token_artifact_count / raw_candidate_count) if raw_candidate_count > 0 else 0.0

    nontrivial_repo = scanned_file_count >= 8
    if nontrivial_repo and validated_code_rule_count <= 0:
        reasons.append(RC_CODE_QUALITY_INSUFFICIENT)
    if raw_candidate_count > 500 and valid_rule_ratio < 0.05:
        reasons.append(RC_CODE_QUALITY_INSUFFICIENT)
    if artifact_ratio > 0.20:
        reasons.append(RC_CODE_QUALITY_INSUFFICIENT)

    if not extraction_ran:
        quality_grade = "fail"
    elif RC_CODE_QUALITY_INSUFFICIENT in reasons or RC_CODE_COVERAGE_INSUFFICIENT in reasons:
        quality_grade = "poor"
    elif valid_rule_ratio >= 0.25 and artifact_ratio <= 0.05:
        quality_grade = "high"
    else:
        quality_grade = "moderate"

    surface_type_distribution: dict[str, int] = {}
    for surface in scanned_surfaces:
        surface_type_distribution[surface.surface_type] = surface_type_distribution.get(surface.surface_type, 0) + 1

    return CodeExtractionCoverage(
        scanned_surfaces=tuple(scanned_surfaces),
        scanned_file_count=scanned_file_count,
        candidate_count=raw_candidate_count,
        missing_expected_surfaces=tuple(sorted(set(missing_expected_surfaces))),
        reason_codes=tuple(dict.fromkeys(reasons)),
        is_sufficient=(len(reasons) == 0),
        raw_candidate_count=raw_candidate_count,
        validated_code_rule_count=max(validated_code_rule_count, 0),
        invalid_code_candidate_count=max(invalid_code_candidate_count, 0),
        code_token_artifact_count=max(code_token_artifact_count, 0),
        valid_rule_ratio=max(valid_rule_ratio, 0.0),
        artifact_ratio=max(artifact_ratio, 0.0),
        coverage_quality_grade=quality_grade,
        semantic_type_distribution=dict(semantic_type_distribution or {}),
        surface_type_distribution=surface_type_distribution,
    )


def coverage_to_payload(coverage: CodeExtractionCoverage) -> dict[str, object]:
    return {
        "scanned_file_count": coverage.scanned_file_count,
        "candidate_count": coverage.candidate_count,
        "raw_candidate_count": coverage.raw_candidate_count,
        "validated_code_rule_count": coverage.validated_code_rule_count,
        "invalid_code_candidate_count": coverage.invalid_code_candidate_count,
        "code_token_artifact_count": coverage.code_token_artifact_count,
        "valid_rule_ratio": coverage.valid_rule_ratio,
        "artifact_ratio": coverage.artifact_ratio,
        "coverage_quality_grade": coverage.coverage_quality_grade,
        "missing_expected_surfaces": list(coverage.missing_expected_surfaces),
        "reason_codes": list(coverage.reason_codes),
        "is_sufficient": coverage.is_sufficient,
        "semantic_type_distribution": dict(coverage.semantic_type_distribution or {}),
        "surface_type_distribution": dict(coverage.surface_type_distribution or {}),
        "scanned_surfaces": [
            {
                "path": item.path,
                "language": item.language,
                "surface_type": item.surface_type,
            }
            for item in coverage.scanned_surfaces
        ],
    }
