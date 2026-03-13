from __future__ import annotations

from governance.engine.business_rules_code_extraction import CodeSurface
from governance.engine.business_rules_coverage import (
    RC_CODE_COVERAGE_INSUFFICIENT,
    RC_CODE_EXTRACTION_NOT_RUN,
    RC_CODE_PROVENANCE_MISSING,
    evaluate_code_extraction_coverage,
)


def test_happy_coverage_sufficient_with_surfaces_and_candidates() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=[
            CodeSurface(path="src/policy.py", language="python", surface_type="permissions"),
            CodeSurface(path="src/validator.py", language="python", surface_type="validator"),
            CodeSurface(path="src/workflow.py", language="python", surface_type="workflow"),
        ],
        candidate_count=2,
        extraction_ran=True,
    )

    assert coverage.is_sufficient is True
    assert coverage.reason_codes == ()


def test_bad_coverage_when_extraction_not_run() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=[],
        candidate_count=0,
        extraction_ran=False,
    )

    assert coverage.is_sufficient is False
    assert RC_CODE_EXTRACTION_NOT_RUN in coverage.reason_codes


def test_corner_coverage_insufficient_when_code_exists_but_no_candidates() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=[
            CodeSurface(path="src/service.py", language="python", surface_type="service"),
        ],
        candidate_count=0,
        extraction_ran=True,
    )

    assert coverage.is_sufficient is False
    assert RC_CODE_COVERAGE_INSUFFICIENT in coverage.reason_codes


def test_edge_coverage_flags_provenance_gap() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=[
            CodeSurface(path="src/policy.py", language="python", surface_type="permissions"),
        ],
        candidate_count=1,
        extraction_ran=True,
        has_provenance_gaps=True,
    )

    assert coverage.is_sufficient is False
    assert RC_CODE_PROVENANCE_MISSING in coverage.reason_codes


def test_corner_missing_expected_surfaces_can_block_sufficiency() -> None:
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=[
            CodeSurface(path="src/policy.py", language="python", surface_type="permissions"),
            CodeSurface(path="src/service.py", language="python", surface_type="service"),
        ],
        candidate_count=2,
        extraction_ran=True,
    )

    assert coverage.is_sufficient is False
    assert RC_CODE_COVERAGE_INSUFFICIENT in coverage.reason_codes
    assert "validator" in coverage.missing_expected_surfaces
    assert "workflow" in coverage.missing_expected_surfaces
