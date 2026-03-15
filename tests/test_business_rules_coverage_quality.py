from __future__ import annotations

from governance.engine.business_rules_code_extraction import CodeSurface
from governance.engine.business_rules_coverage import (
    RC_CODE_COVERAGE_INSUFFICIENT,
    RC_CODE_TEMPLATE_OVERFIT,
    RC_CODE_TOKEN_ARTIFACT_SPIKE,
    RC_CODE_QUALITY_INSUFFICIENT,
    reconcile_code_extraction_coverage,
    evaluate_code_extraction_coverage,
)


def _surfaces() -> list[CodeSurface]:
    base = [
        CodeSurface(path="src/validator.py", language="python", surface_type="validator"),
        CodeSurface(path="src/policy.py", language="python", surface_type="permissions"),
        CodeSurface(path="src/workflow.py", language="python", surface_type="workflow"),
        CodeSurface(path="src/service.py", language="python", surface_type="service"),
        CodeSurface(path="src/model.py", language="python", surface_type="model"),
        CodeSurface(path="src/config.py", language="python", surface_type="config"),
        CodeSurface(path="src/audit.py", language="python", surface_type="service"),
        CodeSurface(path="src/retention.py", language="python", surface_type="service"),
    ]
    extra = [
        CodeSurface(path=f"src/extra_{idx}.py", language="python", surface_type="service")
        for idx in range(12)
    ]
    return [*base, *extra]


def _large_surfaces() -> list[CodeSurface]:
    strong = [
        CodeSurface(path="src/validator.py", language="python", surface_type="validator"),
        CodeSurface(path="src/policy.py", language="python", surface_type="permissions"),
        CodeSurface(path="src/workflow.py", language="python", surface_type="workflow"),
    ]
    rest = [
        CodeSurface(path=f"src/service_{idx}.py", language="python", surface_type="service")
        for idx in range(47)
    ]
    return [*strong, *rest]


def test_massive_raw_candidates_with_zero_valid_is_insufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_large_surfaces(),
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
        scanned_surfaces=_large_surfaces(),
        candidate_count=200,
        extraction_ran=True,
        validated_code_rule_count=30,
        invalid_code_candidate_count=170,
        code_token_artifact_count=50,
    )
    assert coverage.is_sufficient is False
    assert coverage.artifact_ratio > 0.20
    assert RC_CODE_TOKEN_ARTIFACT_SPIKE in coverage.reason_codes


def test_artifact_spike_emits_specific_reason() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_surfaces(),
        candidate_count=200,
        extraction_ran=True,
        validated_code_rule_count=30,
        invalid_code_candidate_count=170,
        code_token_artifact_count=32,
    )
    assert coverage.is_sufficient is False
    assert RC_CODE_TOKEN_ARTIFACT_SPIKE in coverage.reason_codes
    assert coverage.artifact_ratio < 0.20


def test_template_overfit_is_insufficient() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_surfaces(),
        candidate_count=20,
        extraction_ran=True,
        validated_code_rule_count=2,
        invalid_code_candidate_count=18,
        code_token_artifact_count=0,
        template_overfit_count=2,
    )
    assert coverage.is_sufficient is False
    assert RC_CODE_TEMPLATE_OVERFIT in coverage.reason_codes


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


def test_corner_validation_failure_forces_coverage_poor() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=_surfaces()[:3],
        candidate_count=12,
        extraction_ran=True,
        validated_code_rule_count=8,
        invalid_code_candidate_count=4,
        code_token_artifact_count=0,
    )

    reconciled = reconcile_code_extraction_coverage(
        coverage,
        validation_reason_codes=["BUSINESS_RULES_RENDER_MISMATCH"],
    )

    assert reconciled.is_sufficient is False
    assert reconciled.coverage_quality_grade == "poor"
    assert RC_CODE_COVERAGE_INSUFFICIENT in reconciled.reason_codes
    assert RC_CODE_QUALITY_INSUFFICIENT in reconciled.reason_codes
    assert "validation_render_mismatch" in reconciled.quality_insufficiency_reasons
