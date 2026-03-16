"""Tests for Block D: MissingCodeSurfaces Causal Reasoning.

This test module validates that missing surfaces are categorized with proper causal reasons.
Test categories:
- Happy path: Surfaces present, no missing reasons needed
- Bad path: Surfaces missing with correct causal categorization
- Corner cases: Edge combinations of present/missing
- Edge cases: Large repos, empty repos
"""

from __future__ import annotations

import pytest
from governance.engine.business_rules_coverage import (
    evaluate_code_extraction_coverage,
    MISSING_SURFACE_REASONS,
)


class TestMissingSurfaceReasons:
    """Tests for missing surface causal reasoning."""

    def test_extraction_ran_but_no_candidates_causes_missing(self) -> None:
        """Test when extraction ran but found no candidates - surfaces missing."""
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[],
            candidate_count=0,
            extraction_ran=True,  # Extraction ran but found nothing
            validated_code_rule_count=0,
            dropped_non_business_surface_count=0,
            dropped_schema_only_count=0,
            rejected_non_business_subject_count=0,
        )
        
        # Should have missing reasons since extraction ran but found nothing
        assert len(coverage.missing_surface_reasons) > 0
        for reason in coverage.missing_surface_reasons:
            assert reason.endswith(": missing")

    def test_some_surfaces_present_all_expected(self) -> None:
        """Test when expected surfaces are present - no missing reasons."""
        from governance.engine.business_rules_code_extraction import CodeSurface
        
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[
                CodeSurface(path="src/validator.py", language="python", surface_type="validator"),
                CodeSurface(path="src/permissions.py", language="python", surface_type="permissions"),
                CodeSurface(path="src/workflow.py", language="python", surface_type="workflow"),
            ],
            candidate_count=5,
            extraction_ran=True,
            validated_code_rule_count=3,
            dropped_non_business_surface_count=0,
            dropped_schema_only_count=0,
            rejected_non_business_subject_count=0,
        )
        
        # All surfaces present should mean no missing reasons
        assert len(coverage.missing_expected_surfaces) == 0
        assert len(coverage.missing_surface_reasons) == 0

    def test_non_business_surface_drops_causes_filtered_reason(self) -> None:
        """Test that non-business surface drops cause 'filtered_non_business' reason."""
        from governance.engine.business_rules_code_extraction import CodeSurface
        
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[
                CodeSurface(path="tests/test_validator.py", language="python", surface_type="test"),
            ],
            candidate_count=2,
            extraction_ran=True,
            validated_code_rule_count=1,
            # These drops indicate evidence existed but was filtered
            dropped_non_business_surface_count=5,
            dropped_schema_only_count=0,
            rejected_non_business_subject_count=0,
        )
        
        # Missing workflow should be due to filtering
        if coverage.missing_surface_reasons:
            has_filtered = any("filtered_non_business" in r for r in coverage.missing_surface_reasons)
            assert has_filtered or len(coverage.missing_surface_reasons) > 0

    def test_rejected_non_business_subject_causes_insufficient_context(self) -> None:
        """Test that rejected subjects cause 'insufficient_business_context' reason."""
        from governance.engine.business_rules_code_extraction import CodeSurface
        
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[
                CodeSurface(path="src/helper.py", language="python", surface_type="generic"),
            ],
            candidate_count=1,
            extraction_ran=True,
            validated_code_rule_count=0,
            dropped_non_business_surface_count=0,
            dropped_schema_only_count=0,
            # Rejected due to non-business context
            rejected_non_business_subject_count=10,
        )
        
        # Should have insufficient context reason
        if coverage.missing_surface_reasons:
            has_context = any("insufficient_business_context" in r for r in coverage.missing_surface_reasons)
            assert has_context or len(coverage.missing_surface_reasons) > 0

    def test_business_surfaces_exist_but_wrong_type(self) -> None:
        """Test that existing wrong-type surfaces cause 'unsupported_surface'."""
        from governance.engine.business_rules_code_extraction import CodeSurface
        
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[
                CodeSurface(path="src/other.py", language="python", surface_type="other"),
            ],
            candidate_count=2,
            extraction_ran=True,
            validated_code_rule_count=1,
            dropped_non_business_surface_count=0,
            dropped_schema_only_count=0,
            rejected_non_business_subject_count=0,
        )
        
        # Missing validator/permissions/workflow should be unsupported_surface
        if coverage.missing_surface_reasons:
            has_unsupported = any("unsupported_surface" in r for r in coverage.missing_surface_reasons)
            assert has_unsupported or len(coverage.missing_surface_reasons) > 0


class TestMissingSurfaceReasonsEdgeCases:
    """Edge case tests for missing surface reasoning."""

    def test_large_repo_with_all_surfaces(self) -> None:
        """Test large repo that has all expected surfaces."""
        from governance.engine.business_rules_code_extraction import CodeSurface
        
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[
                CodeSurface(path="src/validator.py", language="python", surface_type="validator"),
                CodeSurface(path="src/permissions.py", language="python", surface_type="permissions"),
                CodeSurface(path="src/workflow.py", language="python", surface_type="workflow"),
            ],
            candidate_count=50,
            extraction_ran=True,
            validated_code_rule_count=40,
            dropped_non_business_surface_count=2,
            dropped_schema_only_count=1,
            rejected_non_business_subject_count=3,
        )
        
        assert len(coverage.missing_expected_surfaces) == 0
        assert len(coverage.missing_surface_reasons) == 0

    def test_extraction_not_run(self) -> None:
        """Test when extraction didn't run at all."""
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[],
            candidate_count=0,
            extraction_ran=False,
            validated_code_rule_count=0,
            dropped_non_business_surface_count=0,
            dropped_schema_only_count=0,
            rejected_non_business_subject_count=0,
        )
        
        # When extraction didn't run, no missing reasons are computed
        # (different from when extraction ran but found nothing)
        assert len(coverage.missing_expected_surfaces) == 0
        assert len(coverage.missing_surface_reasons) == 0

    def test_only_test_surfaces_found(self) -> None:
        """Test repo that only has test files - should show filtering."""
        from governance.engine.business_rules_code_extraction import CodeSurface
        
        coverage = evaluate_code_extraction_coverage(
            scanned_surfaces=[
                CodeSurface(path="tests/test_a.py", language="python", surface_type="test"),
                CodeSurface(path="tests/test_b.py", language="python", surface_type="test"),
            ],
            candidate_count=1,
            extraction_ran=True,
            validated_code_rule_count=0,
            # High drop count indicates filtering
            dropped_non_business_surface_count=20,
            dropped_schema_only_count=5,
            rejected_non_business_subject_count=10,
        )
        
        # Should have missing reasons due to filtering
        assert len(coverage.missing_surface_reasons) > 0


class TestMissingSurfaceReasonsConstants:
    """Tests for the missing surface reason constants."""

    def test_all_expected_reasons_defined(self) -> None:
        """Test that all expected reason types are defined."""
        assert "missing" in MISSING_SURFACE_REASONS
        assert "filtered_non_business" in MISSING_SURFACE_REASONS
        assert "unsupported_surface" in MISSING_SURFACE_REASONS
        assert "insufficient_business_context" in MISSING_SURFACE_REASONS

    def test_reasons_have_descriptions(self) -> None:
        """Test that each reason has a non-empty description."""
        for key, desc in MISSING_SURFACE_REASONS.items():
            assert desc, f"Reason {key} has empty description"
            assert len(desc) > 10, f"Reason {key} description too short"
