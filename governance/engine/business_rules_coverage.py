from __future__ import annotations

from dataclasses import dataclass

from governance.engine.business_rules_code_extraction import CodeSurface


RC_CODE_EXTRACTION_NOT_RUN = "BUSINESS_RULES_CODE_EXTRACTION_NOT_RUN"
RC_CODE_COVERAGE_INSUFFICIENT = "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT"
RC_CODE_PROVENANCE_MISSING = "BUSINESS_RULES_CODE_PROVENANCE_MISSING"
RC_CODE_QUALITY_INSUFFICIENT = "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT"
RC_CODE_TOKEN_ARTIFACT_SPIKE = "BUSINESS_RULES_CODE_TOKEN_ARTIFACT_SPIKE"
RC_CODE_TEMPLATE_OVERFIT = "BUSINESS_RULES_CODE_TEMPLATE_OVERFIT"


# PR5 fixed quality defaults; configurable thresholds are out of scope here.
NONTRIVIAL_REPO_SURFACE_THRESHOLD = 8
LARGE_REPO_CANDIDATE_THRESHOLD = 100
MIN_VALIDATED_CODE_RULE_COUNT_NONTRIVIAL = 1
MIN_VALID_RULE_RATIO_LARGE_REPO = 0.10
MAX_ARTIFACT_RATIO = 0.20
TOKEN_ARTIFACT_SPIKE_THRESHOLD = 0.35
MIN_SEMANTIC_DIVERSITY_SCORE = 0.30
MIN_SURFACE_BALANCE_SCORE = 0.25


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
    surface_balance_score: float = 0.0
    semantic_diversity_score: float = 0.0
    quality_insufficiency_reasons: tuple[str, ...] = ()
    template_overfit_count: int = 0


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
    template_overfit_count: int = 0,
) -> CodeExtractionCoverage:
    reasons: list[str] = []
    quality_reasons: list[str] = []
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

    nontrivial_repo = scanned_file_count >= NONTRIVIAL_REPO_SURFACE_THRESHOLD
    if nontrivial_repo and validated_code_rule_count < MIN_VALIDATED_CODE_RULE_COUNT_NONTRIVIAL:
        quality_reasons.append("validated_code_rule_count_below_minimum")
    if raw_candidate_count >= LARGE_REPO_CANDIDATE_THRESHOLD and valid_rule_ratio < MIN_VALID_RULE_RATIO_LARGE_REPO:
        quality_reasons.append("valid_rule_ratio_below_threshold")
    if artifact_ratio > MAX_ARTIFACT_RATIO:
        quality_reasons.append("artifact_ratio_above_maximum")

    total_semantic = sum(int(v) for v in (semantic_type_distribution or {}).values())
    if total_semantic > 0:
        semantic_max = max(int(v) for v in (semantic_type_distribution or {}).values())
        semantic_diversity_score = 1.0 - (semantic_max / total_semantic)
    else:
        semantic_diversity_score = 0.0

    surface_type_distribution: dict[str, int] = {}
    for surface in scanned_surfaces:
        surface_type_distribution[surface.surface_type] = surface_type_distribution.get(surface.surface_type, 0) + 1
    total_surfaces = sum(surface_type_distribution.values())
    if total_surfaces > 0:
        surface_max = max(surface_type_distribution.values())
        surface_balance_score = 1.0 - (surface_max / total_surfaces)
    else:
        surface_balance_score = 0.0

    if raw_candidate_count >= 20 and semantic_diversity_score < MIN_SEMANTIC_DIVERSITY_SCORE:
        quality_reasons.append("semantic_diversity_too_low")
    if nontrivial_repo and surface_balance_score < MIN_SURFACE_BALANCE_SCORE:
        quality_reasons.append("surface_balance_too_low")

    if artifact_ratio > TOKEN_ARTIFACT_SPIKE_THRESHOLD:
        reasons.append(RC_CODE_TOKEN_ARTIFACT_SPIKE)
        quality_reasons.append("token_artifact_spike")
    if template_overfit_count > 0 and template_overfit_count >= max(validated_code_rule_count, 1):
        reasons.append(RC_CODE_TEMPLATE_OVERFIT)
        quality_reasons.append("template_overfit")

    if quality_reasons and RC_CODE_QUALITY_INSUFFICIENT not in reasons:
        reasons.append(RC_CODE_QUALITY_INSUFFICIENT)

    if not extraction_ran:
        quality_grade = "fail"
    elif RC_CODE_QUALITY_INSUFFICIENT in reasons or RC_CODE_COVERAGE_INSUFFICIENT in reasons:
        quality_grade = "poor"
    elif valid_rule_ratio >= 0.25 and artifact_ratio <= 0.05:
        quality_grade = "high"
    else:
        quality_grade = "moderate"

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
        surface_balance_score=max(surface_balance_score, 0.0),
        semantic_diversity_score=max(semantic_diversity_score, 0.0),
        quality_insufficiency_reasons=tuple(quality_reasons),
        template_overfit_count=max(template_overfit_count, 0),
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
        "surface_balance_score": coverage.surface_balance_score,
        "semantic_diversity_score": coverage.semantic_diversity_score,
        "quality_insufficiency_reasons": list(coverage.quality_insufficiency_reasons),
        "template_overfit_count": coverage.template_overfit_count,
        "scanned_surfaces": [
            {
                "path": item.path,
                "language": item.language,
                "surface_type": item.surface_type,
            }
            for item in coverage.scanned_surfaces
        ],
    }
