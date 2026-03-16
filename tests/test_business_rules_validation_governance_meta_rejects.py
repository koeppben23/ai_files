"""Tests for Block B: Validation tighter - Governance/Meta rejects.

This test module validates that governance and meta rules are rejected during validation.
Test categories:
- Happy path: Actual business rules pass validation
- Bad path: Governance/meta rules are rejected
- Corner cases: Mixed sources, edge patterns
- Edge cases: Complex paths, unusual filenames
"""

from __future__ import annotations

import pytest
from governance.engine.business_rules_validation import (
    _validate_rule_text,
    REASON_GOVERNANCE_META_RULE,
    REASON_NON_BUSINESS_SUBJECT,
    ORIGIN_CODE,
)


class TestGovernanceMetaRejects:
    """Tests for governance/meta rule rejection."""

    def test_phase_api_yaml_rejected(self) -> None:
        """Test that rules from phase_api.yaml are rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Phase transitions must follow defined workflow",
            origin=ORIGIN_CODE,
            semantic_type="transition",
            source_path="governance/phase_api.yaml",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_reason_codes_registry_rejected(self) -> None:
        """Test that rules from reason_codes.registry.json are rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-002: All rules must have registered reason codes",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            source_path="governance/reason_codes.registry.json",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_session_state_schema_rejected(self) -> None:
        """Test that rules from SESSION_STATE_SCHEMA.md are rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-003: Session state must conform to schema",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            source_path="docs/SESSION_STATE_SCHEMA.md",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_governance_policy_yaml_rejected(self) -> None:
        """Test that rules from governance policy files are rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-004: Policies must be enforced",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            source_path="governance/policy.yaml",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_actual_business_rule_accepted(self) -> None:
        """Test that actual business rules are accepted."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Customer ID must be present",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validators.py",
        )
        assert ok is True
        assert reason_code == "none"


class TestGovernanceMetaSubjects:
    """Tests for governance/meta subject rejection."""

    def test_session_state_subject_rejected(self) -> None:
        """Test that session_state subject without business context is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Session state must be valid",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validation.py",
        )
        assert ok is False
        assert reason_code == REASON_NON_BUSINESS_SUBJECT

    def test_payload_subject_rejected(self) -> None:
        """Test that payload subject without business context is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-002: Payload must be validated",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validation.py",
        )
        assert ok is False
        assert reason_code == REASON_NON_BUSINESS_SUBJECT

    def test_phase_subject_rejected(self) -> None:
        """Test that phase subject without business context is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-003: Phase must be valid",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validation.py",
        )
        assert ok is False
        assert reason_code == REASON_NON_BUSINESS_SUBJECT

    def test_reason_code_subject_rejected(self) -> None:
        """Test that reason_code subject without business context is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-004: Reason code must be provided",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validation.py",
        )
        assert ok is False
        assert reason_code == REASON_NON_BUSINESS_SUBJECT

    def test_schema_subject_rejected(self) -> None:
        """Test that schema subject without business context is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-005: Schema must be defined",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validation.py",
        )
        assert ok is False
        assert reason_code == REASON_NON_BUSINESS_SUBJECT

    def test_gate_subject_rejected(self) -> None:
        """Test that gate subject without business context is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-006: Gate must be passed",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="src/validation.py",
        )
        assert ok is False
        assert reason_code == REASON_NON_BUSINESS_SUBJECT


class TestGovernanceMetaEdgeCases:
    """Edge case tests for governance/meta rejection."""

    def test_case_insensitive_path_matching(self) -> None:
        """Test that path matching is case-insensitive."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Rule must be enforced",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            source_path="GOVERNANCE/PHASE_API.YAML",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_nested_governance_path(self) -> None:
        """Test that nested governance paths are rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Rule must be enforced",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            source_path="config/governance/phase.yaml",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_registry_json_rejected(self) -> None:
        """Test that any registry.json file is rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Rules must be registered",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            source_path="config/registry.json",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE

    def test_no_source_path_accepted(self) -> None:
        """Test that rules without source path are not rejected by governance check."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Customer must be verified",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="",
        )
        # Should not be rejected for governance reasons
        assert reason_code != REASON_GOVERNANCE_META_RULE

    def test_business_rule_in_governance_folder_still_rejected(self) -> None:
        """Test that even business rules in governance folders are rejected."""
        ok, reason_code, reason = _validate_rule_text(
            "BR-001: Customer validation must run",
            origin=ORIGIN_CODE,
            semantic_type="permission",
            evidence_kind="executable_code",
            source_path="governance/validators.py",
        )
        assert ok is False
        assert reason_code == REASON_GOVERNANCE_META_RULE
