"""Tests for business specificity in validation."""

import pytest
from governance.engine.business_rules_validation import (
    validate_candidates,
    RuleCandidate,
    ORIGIN_CODE,
    REASON_NON_BUSINESS_SUBJECT,
    REASON_SCHEMA_ONLY_RULE,
    REASON_NON_EXECUTABLE_EVIDENCE
)


def test_non_business_subject_is_rejected():
    """Rules with non-business subjects should be rejected."""
    candidate = RuleCandidate(
        text="BR-C001: Payload must validate before processing.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="required-field"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be rejected due to non-business subject
    assert len(report.invalid_rules) > 0
    assert report.invalid_rules[0].reason_code == REASON_NON_BUSINESS_SUBJECT


def test_schema_only_rule_is_rejected():
    """Schema-only rules without business context should be rejected."""
    candidate = RuleCandidate(
        text="BR-C002: Required fields must be validated before processing.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="required-field"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be rejected due to schema-only rule OR non-business subject
    # (both "fields" and the schema pattern trigger rejection)
    assert len(report.invalid_rules) > 0
    assert report.invalid_rules[0].reason_code in (REASON_SCHEMA_ONLY_RULE, REASON_NON_BUSINESS_SUBJECT)


def test_actual_business_rule_is_accepted():
    """Actual business rules should be accepted."""
    candidate = RuleCandidate(
        text="BR-C003: Customer ID must be present before processing.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="required-field"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be accepted
    assert len(report.valid_rules) > 0
    assert report.valid_rules[0].text == "BR-C003: Customer ID must be present before processing."


def test_payload_rule_without_business_context_is_rejected():
    """Payload rules without business context should be rejected."""
    candidate = RuleCandidate(
        text="BR-C004: Payload must be validated.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="required-field"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be rejected due to non-business subject
    assert len(report.invalid_rules) > 0
    assert report.invalid_rules[0].reason_code == REASON_NON_BUSINESS_SUBJECT


def test_value_rule_without_business_context_is_rejected():
    """Value rules without business context should be rejected."""
    candidate = RuleCandidate(
        text="BR-C005: Value must not be null.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="invariant"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be rejected due to non-business subject
    assert len(report.invalid_rules) > 0
    assert report.invalid_rules[0].reason_code == REASON_NON_BUSINESS_SUBJECT


def test_field_rule_without_business_context_is_rejected():
    """Field rules without business context should be rejected."""
    candidate = RuleCandidate(
        text="BR-C006: Field is required.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="required-field"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be rejected due to non-business subject
    assert len(report.invalid_rules) > 0
    assert report.invalid_rules[0].reason_code == REASON_NON_BUSINESS_SUBJECT


def test_customer_id_rule_is_accepted():
    """Customer ID rules should be accepted."""
    candidate = RuleCandidate(
        text="BR-C007: Customer ID must be present before processing.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="required-field"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be accepted
    assert len(report.valid_rules) > 0
    assert report.valid_rules[0].text == "BR-C007: Customer ID must be present before processing."


def test_order_total_rule_is_accepted():
    """Order total rules should be accepted."""
    candidate = RuleCandidate(
        text="BR-C008: Order total must be greater than zero.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="invariant"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be accepted
    assert len(report.valid_rules) > 0
    assert report.valid_rules[0].text == "BR-C008: Order total must be greater than zero."


def test_permission_rule_is_accepted():
    """Permission rules should be accepted."""
    candidate = RuleCandidate(
        text="BR-C009: Access control must deny unauthorized operations.",
        source_path="service.py",
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="permission"
    )
    
    report = validate_candidates(candidates=[candidate], has_code_extraction=True)
    # Should be accepted
    assert len(report.valid_rules) > 0
    assert report.valid_rules[0].text == "BR-C009: Access control must deny unauthorized operations."