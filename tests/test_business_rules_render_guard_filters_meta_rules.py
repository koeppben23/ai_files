"""Tests for Block C: Render/Segmentation Guard.

This test module validates that only rules with proper business domain context
enter the render/segmentation pipeline.
Test categories:
- Happy path: Business rules pass to render
- Bad path: Meta/Non-business rules blocked from render
- Corner cases: Mixed evidence kinds, edge semantic types
- Edge cases: Edge combinations
"""

from __future__ import annotations

import pytest
from governance.engine.business_rules_validation import (
    RuleCandidate,
    validate_candidates,
    ORIGIN_CODE,
    ORIGIN_DOC,
)


def _candidate(
    text: str,
    origin: str = ORIGIN_CODE,
    semantic_type: str = "permission",
    evidence_kind: str = "executable_code",
    source_path: str = "src/policy.py",
) -> RuleCandidate:
    return RuleCandidate(
        text=text,
        source_path=source_path,
        line_no=1,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=origin,
        enforcement_anchor_type="validator" if origin == ORIGIN_CODE else "",
        semantic_type=semantic_type,
        evidence_kind=evidence_kind,
    )


class TestRenderGuardHappyPath:
    """Tests for happy path - business rules reach render."""

    def test_valid_code_rule_with_executable_evidence(self) -> None:
        """Test that code rules with executable evidence pass to render."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Customer ID must be present",
                    semantic_type="permission",
                    evidence_kind="executable_code",
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 1
        assert report.invalid_rule_count == 0

    def test_valid_code_rule_with_business_semantics(self) -> None:
        """Test that code rules with valid business semantic type pass."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-002: Order status must be valid",
                    semantic_type="transition",
                    evidence_kind="executable_code",
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 1

    def test_doc_rules_pass_through(self) -> None:
        """Test that doc-origin rules pass through."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-003: Access must be authenticated",
                    origin=ORIGIN_DOC,
                    semantic_type="",
                    evidence_kind="",
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 1


class TestRenderGuardBlocked:
    """Tests for blocked path - meta/non-business rules don't reach render."""

    def test_code_rule_without_executable_evidence_blocked(self) -> None:
        """Test that code rules without executable evidence are blocked."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Customer ID must be present",
                    semantic_type="permission",
                    evidence_kind="comment",  # Not executable
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 0
        assert report.invalid_rule_count >= 1

    def test_code_rule_with_invalid_semantic_type_blocked(self) -> None:
        """Test that code rules with invalid semantic type are blocked."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Something must happen",
                    semantic_type="unknown_type",  # Invalid
                    evidence_kind="executable_code",
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 0
        assert report.invalid_rule_count >= 1

    def test_code_rule_with_empty_semantic_type_blocked(self) -> None:
        """Test that code rules with empty semantic type are blocked."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Something must happen",
                    semantic_type="",  # Empty
                    evidence_kind="executable_code",
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 0
        # Empty semantic type causes dropped_candidate_count (before validation)
        assert report.dropped_candidate_count >= 1 or report.invalid_rule_count >= 1


class TestRenderGuardEdgeCases:
    """Edge case tests for render guard."""

    def test_mixed_valid_and_invalid_candidates(self) -> None:
        """Test that mixed candidates are handled correctly."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Customer ID must be present",
                    semantic_type="permission",
                    evidence_kind="executable_code",
                ),
                _candidate(
                    "BR-002: Some rule without evidence",
                    semantic_type="permission",
                    evidence_kind="",
                ),
                _candidate(
                    "BR-003: Order status must be valid",
                    semantic_type="transition",
                    evidence_kind="executable_code",
                ),
            ],
            has_code_extraction=True,
        )
        # Only valid ones should pass
        assert report.valid_rule_count == 2
        assert report.invalid_rule_count >= 1

    def test_governance_path_still_blocked_after_validation(self) -> None:
        """Test that governance path rules are blocked even if they pass text validation."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Phase must be valid",
                    semantic_type="permission",
                    evidence_kind="executable_code",
                    source_path="governance/phase_api.yaml",
                ),
            ],
            has_code_extraction=True,
        )
        # Should be blocked by governance pattern check
        assert report.valid_rule_count == 0

    def test_actual_business_rule_from_src_passes(self) -> None:
        """Test that actual business rules from src/ pass."""
        report = validate_candidates(
            candidates=[
                _candidate(
                    "BR-001: Payment must be validated",
                    semantic_type="permission",
                    evidence_kind="executable_code",
                    source_path="src/payment.py",
                ),
            ],
            has_code_extraction=True,
        )
        assert report.valid_rule_count == 1
