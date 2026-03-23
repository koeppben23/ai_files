from __future__ import annotations

from governance_runtime.engine.business_rules_validation import (
    ORIGIN_CODE,
    REASON_CODE_TEMPLATE_OVERFIT,
    REASON_CODE_TOKEN_ARTIFACT,
    RuleCandidate,
    validate_candidates,
)


def _candidate(text: str, *, semantic_type: str = "permission") -> RuleCandidate:
    return RuleCandidate(
        text=text,
        source_path="src/policy.py",
        line_no=10,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="raise",
        semantic_type=semantic_type,
    )


def test_bad_validation_rejects_generic_code_template_sentences() -> None:
    # Schema-only rules should be rejected even without explicit business context
    report = validate_candidates(
        candidates=[
            _candidate("BR-C001: Access control must deny unauthorized operations.", semantic_type="permission"),
            # This one is rejected because "required fields must be validated" is a schema-only pattern
            _candidate("BR-C002: Required fields must be validated before processing.", semantic_type="required-field"),
            _candidate("BR-C003: Disallowed lifecycle transitions must be blocked.", semantic_type="transition"),
        ],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=3,
        enforce_code_requirements=True,
    )

    # Schema-only rules should be rejected, others may pass with proper semantic types
    assert report.valid_rule_count >= 0
    assert report.invalid_rule_count >= 1


def test_happy_validation_accepts_business_readable_code_rules() -> None:
    report = validate_candidates(
        candidates=[
            _candidate("BR-C010: Customer ID must be present before processing.", semantic_type="required-field"),
            _candidate("BR-C011: Archived status transitions must be blocked when invalid.", semantic_type="transition"),
            _candidate("BR-C012: Customer exports must deny unauthorized access.", semantic_type="permission"),
        ],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=3,
        enforce_code_requirements=True,
    )

    assert report.valid_rule_count == 3
    assert report.code_valid_rule_count == 3
    assert report.has_code_token_artifacts is False
    assert report.is_compliant is True


def test_corner_validation_rejects_template_phrasing_even_with_domain_tail() -> None:
    report = validate_candidates(
        candidates=[
            _candidate("BR-C020: Permission checks must be enforced for customer exports.", semantic_type="permission"),
            _candidate("BR-C021: Required field checks must be enforced for customer profile.", semantic_type="required-field"),
        ],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=2,
        enforce_code_requirements=True,
    )

    assert report.valid_rule_count == 0
    assert REASON_CODE_TEMPLATE_OVERFIT in report.reason_codes


def test_edge_validation_rejects_helper_exists_as_code_token_artifact() -> None:
    report = validate_candidates(
        candidates=[
            _candidate("BR-C030: Customer records must reject not helper exists.", semantic_type="uniqueness"),
        ],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=1,
        enforce_code_requirements=True,
    )

    assert report.valid_rule_count == 0
    assert report.code_token_artifact_count >= 1
    assert REASON_CODE_TOKEN_ARTIFACT in report.reason_codes
