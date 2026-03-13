from __future__ import annotations

from governance.engine.business_rules_code_extraction import CodeSurface
from governance.engine.business_rules_coverage import (
    MAX_ARTIFACT_RATIO,
    MIN_VALID_RULE_RATIO_LARGE_REPO,
    RC_CODE_QUALITY_INSUFFICIENT,
    evaluate_code_extraction_coverage,
)


def _large_surfaces() -> list[CodeSurface]:
    return [CodeSurface(path=f"src/s{i}.py", language="python", surface_type="service") for i in range(12)]


def test_edge_artifact_ratio_just_below_threshold_can_pass() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_large_surfaces(),
        candidate_count=100,
        extraction_ran=True,
        validated_code_rule_count=25,
        invalid_code_candidate_count=75,
        code_token_artifact_count=int(MAX_ARTIFACT_RATIO * 100),
        semantic_type_distribution={"permission": 10, "required-field": 8, "audit": 7},
    )
    assert coverage.artifact_ratio == MAX_ARTIFACT_RATIO


def test_bad_low_valid_ratio_in_large_repo_is_insufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_large_surfaces(),
        candidate_count=100,
        extraction_ran=True,
        validated_code_rule_count=int(MIN_VALID_RULE_RATIO_LARGE_REPO * 100) - 1,
        invalid_code_candidate_count=91,
        code_token_artifact_count=0,
        semantic_type_distribution={"permission": 1, "required-field": 1, "audit": 7},
    )
    assert coverage.is_sufficient is False
    assert RC_CODE_QUALITY_INSUFFICIENT in coverage.reason_codes


def test_corner_low_semantic_diversity_is_insufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_large_surfaces(),
        candidate_count=40,
        extraction_ran=True,
        validated_code_rule_count=8,
        invalid_code_candidate_count=32,
        code_token_artifact_count=2,
        semantic_type_distribution={"permission": 39, "audit": 1},
    )
    assert coverage.is_sufficient is False
    assert "semantic_diversity_too_low" in coverage.quality_insufficiency_reasons


def test_happy_balanced_semantics_can_be_sufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=[
            CodeSurface(path="src/v.py", language="python", surface_type="validator"),
            CodeSurface(path="src/p.py", language="python", surface_type="permissions"),
            CodeSurface(path="src/w.py", language="python", surface_type="workflow"),
        ],
        candidate_count=30,
        extraction_ran=True,
        validated_code_rule_count=12,
        invalid_code_candidate_count=18,
        code_token_artifact_count=2,
        semantic_type_distribution={"permission": 10, "required-field": 10, "transition": 10},
    )
    assert coverage.is_sufficient is True
