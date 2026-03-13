from __future__ import annotations

from governance.engine.business_rules_code_extraction import CodeSurface
from governance.engine.business_rules_coverage import (
    RC_CODE_QUALITY_INSUFFICIENT,
    evaluate_code_extraction_coverage,
)


def _surfaces() -> list[CodeSurface]:
    return [
        CodeSurface(path="src/validator.py", language="python", surface_type="validator"),
        CodeSurface(path="src/policy.py", language="python", surface_type="permissions"),
        CodeSurface(path="src/workflow.py", language="python", surface_type="workflow"),
        CodeSurface(path="src/service.py", language="python", surface_type="service"),
        CodeSurface(path="src/model.py", language="python", surface_type="model"),
        CodeSurface(path="src/config.py", language="python", surface_type="config"),
        CodeSurface(path="src/audit.py", language="python", surface_type="service"),
        CodeSurface(path="src/retention.py", language="python", surface_type="service"),
    ]


def test_massive_raw_candidates_with_zero_valid_is_insufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_surfaces(),
        candidate_count=4096,
        extraction_ran=True,
        validated_code_rule_count=0,
        invalid_code_candidate_count=4096,
        code_token_artifact_count=1200,
    )
    assert coverage.is_sufficient is False
    assert RC_CODE_QUALITY_INSUFFICIENT in coverage.reason_codes


def test_high_artifact_ratio_is_insufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_surfaces(),
        candidate_count=200,
        extraction_ran=True,
        validated_code_rule_count=30,
        invalid_code_candidate_count=170,
        code_token_artifact_count=60,
    )
    assert coverage.is_sufficient is False
    assert coverage.artifact_ratio > 0.20


def test_few_high_quality_rules_can_be_sufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_surfaces()[:3],
        candidate_count=12,
        extraction_ran=True,
        validated_code_rule_count=8,
        invalid_code_candidate_count=4,
        code_token_artifact_count=0,
    )
    assert coverage.is_sufficient is True
    assert coverage.valid_rule_ratio > 0.5
