from __future__ import annotations

from governance.engine.business_rules_coverage import reconcile_code_extraction_payload
from governance.engine.business_rules_validation import ORIGIN_CODE, RuleCandidate, validate_candidates


def _code_candidate(text: str) -> RuleCandidate:
    return RuleCandidate(
        text=text,
        source_path="src/policy.py",
        line_no=10,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="permission",
    )


def test_render_mismatch_forces_quality_insufficiency() -> None:
    report = validate_candidates(
        candidates=[_code_candidate("BR-C001: Access control must deny unauthorized operations.")],
        expected_rules=False,
        rendered_rules=["BR-C999: Wrong rule"],
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=1,
        enforce_code_requirements=True,
    )

    assert report.has_render_mismatch is True
    assert report.has_quality_insufficiency is True
    assert report.code_extraction_sufficient is False
    assert report.has_code_coverage_gap is True


def test_source_violation_forces_quality_insufficiency() -> None:
    violating = RuleCandidate(
        text="BR-C002: Access control must deny unauthorized operations.",
        source_path="tests/rules.md",
        line_no=4,
        source_allowed=False,
        source_reason="disallowed-directory",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="permission",
    )
    report = validate_candidates(
        candidates=[violating],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=1,
        enforce_code_requirements=True,
    )

    assert report.has_source_violation is True
    assert report.has_quality_insufficiency is True
    assert report.code_extraction_sufficient is False


def test_segmentation_failure_forces_quality_insufficiency() -> None:
    report = validate_candidates(
        candidates=[_code_candidate("BR-C003 Access control must deny unauthorized operations")],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=1,
        enforce_code_requirements=True,
    )

    assert report.has_segmentation_failure is True
    assert report.has_quality_insufficiency is True
    assert report.code_extraction_sufficient is False


def test_count_mismatch_forces_quality_insufficiency() -> None:
    report = validate_candidates(
        candidates=[_code_candidate("BR-C004: Customer exports must deny unauthorized access.")],
        expected_rules=False,
        rendered_rules=[
            "BR-C004: Customer exports must deny unauthorized access.",
            "BR-C005: Audit entries must remain immutable.",
        ],
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=1,
        enforce_code_requirements=True,
    )

    assert report.count_consistent is False
    assert report.has_quality_insufficiency is True
    assert report.code_extraction_sufficient is False


def test_edge_payload_reconciliation_forces_poor_coverage() -> None:
    payload = {
        "candidate_count": 8,
        "raw_candidate_count": 8,
        "dropped_candidate_count": 0,
        "reason_codes": [],
        "quality_insufficiency_reasons": [],
        "coverage_quality_grade": "high",
        "is_sufficient": True,
    }

    reconciled = reconcile_code_extraction_payload(
        payload,
        validation_reason_codes=["BUSINESS_RULES_COUNT_MISMATCH"],
    )
    reason_codes = reconciled["reason_codes"]
    quality_reasons = reconciled["quality_insufficiency_reasons"]

    assert reconciled["is_sufficient"] is False
    assert reconciled["coverage_quality_grade"] == "poor"
    assert isinstance(reason_codes, list)
    assert isinstance(quality_reasons, list)
    assert "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT" in reason_codes
    assert "validation_count_mismatch" in quality_reasons
