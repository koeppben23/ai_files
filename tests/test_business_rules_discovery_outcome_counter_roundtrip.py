"""Tests for Block A: Discovery Outcome Counter Roundtrip (SSOT Fix).

This test module validates that discovery outcomes are correctly aggregated
into snapshot counters, ensuring SSOT between:
- code_extraction_report.json
- SESSION_STATE.json
- business-rules-status.md

Test categories:
- Happy path: Normal discovery outcomes with all categories
- Bad path: Invalid/missing data, malformed outcomes
- Corner cases: Empty outcomes, partial data, boundary conditions
- Edge cases: Extreme values, unusual statuses
"""

from __future__ import annotations

import pytest
from governance_runtime.engine.business_rules_hydration import (
    _aggregate_discovery_outcome_counts,
    _build_code_extraction_counters,
    CodeExtractionCounters,
)
from governance_runtime.engine.business_rules_code_extraction import (
    DISCOVERY_ACCEPTED,
    DISCOVERY_DROPPED_NON_BUSINESS_SURFACE,
    DISCOVERY_DROPPED_SCHEMA_ONLY,
    DISCOVERY_DROPPED_NON_EXECUTABLE_NORMATIVE_TEXT,
    DISCOVERY_DROPPED_TECHNICAL,
    DISCOVERY_DROPPED_MISSING_ANCHOR,
    DISCOVERY_DROPPED_MISSING_SEMANTICS,
)


class TestAggregateDiscoveryOutcomeCountsHappyPath:
    """Happy path tests for outcome aggregation."""

    def test_all_categories_present(self) -> None:
        """Test aggregation with all outcome categories present."""
        outcomes = [
            {"status": "accepted_for_validation", "path": "src/auth.py"},
            {"status": "accepted_for_validation", "path": "src/validation.py"},
            {"status": "dropped_non_business_surface", "path": "tests/test_auth.py"},
            {"status": "dropped_schema_only", "path": "config/schema.yaml"},
            {"status": "dropped_non_executable_normative_text", "path": "docs/rules.md"},
            {"status": "dropped_technical_artifact", "path": "src/__init__.py"},
            {"status": "dropped_missing_enforcement_anchor", "path": "src/broken.py"},
            {"status": "dropped_missing_business_semantics", "path": "src/empty.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 8
        assert result["dropped_candidate_count"] == 6
        assert result["accepted_for_validation_count"] == 2
        assert result["dropped_non_business_surface_count"] == 1
        assert result["dropped_schema_only_count"] == 1
        assert result["dropped_non_executable_normative_text_count"] == 1

    def test_only_accepted_outcomes(self) -> None:
        """Test aggregation with only accepted outcomes."""
        outcomes = [
            {"status": "accepted_for_validation", "path": "src/auth.py"},
            {"status": "accepted_for_validation", "path": "src/validation.py"},
            {"status": "accepted_for_validation", "path": "src/workflow.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 3
        assert result["dropped_candidate_count"] == 0
        assert result["accepted_for_validation_count"] == 3
        assert result["dropped_non_business_surface_count"] == 0

    def test_only_dropped_outcomes(self) -> None:
        """Test aggregation with only dropped outcomes."""
        outcomes = [
            {"status": "dropped_non_business_surface", "path": "tests/test_auth.py"},
            {"status": "dropped_schema_only", "path": "config/schema.yaml"},
            {"status": "dropped_technical_artifact", "path": "src/__init__.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 3
        assert result["dropped_candidate_count"] == 3
        assert result["accepted_for_validation_count"] == 0


class TestAggregateDiscoveryOutcomeCountsBadPath:
    """Bad path tests for outcome aggregation - invalid/missing data."""

    def test_empty_outcomes(self) -> None:
        """Test aggregation with empty outcomes list."""
        result = _aggregate_discovery_outcome_counts([])
        
        assert result["raw_candidate_count"] == 0
        assert result["dropped_candidate_count"] == 0
        assert result["accepted_for_validation_count"] == 0
        assert result["dropped_non_business_surface_count"] == 0

    def test_none_outcomes(self) -> None:
        """Test aggregation with None outcomes."""
        result = _aggregate_discovery_outcome_counts(None)
        
        assert result["raw_candidate_count"] == 0

    def test_malformed_outcome_dict(self) -> None:
        """Test aggregation skips malformed outcome dicts."""
        outcomes = [
            {"status": "accepted_for_validation", "path": "src/auth.py"},
            "not a dict",
            None,
            {"path": "src/missing_status.py"},
            {},
            {"status": "dropped_non_business_surface"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        # Non-dict items ("not a dict", None) are skipped
        # Valid dicts: accepted_for_validation, missing_status (empty status), {} (empty), dropped_non_business_surface
        # = 4 dicts counted
        assert result["raw_candidate_count"] == 4
        assert result["accepted_for_validation_count"] == 1
        assert result["dropped_non_business_surface_count"] == 1

    def test_unknown_status_handled(self) -> None:
        """Test aggregation with unknown status values."""
        outcomes = [
            {"status": "accepted_for_validation", "path": "src/auth.py"},
            {"status": "unknown_status", "path": "src/unknown.py"},
            {"status": "", "path": "src/empty.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        # Unknown statuses are counted in raw but not in specific categories
        assert result["raw_candidate_count"] == 3
        assert result["dropped_candidate_count"] == 2  # unknown and empty are dropped


class TestAggregateDiscoveryOutcomeCountsCornerCases:
    """Corner case tests for outcome aggregation."""

    def test_single_outcome_accepted(self) -> None:
        """Test aggregation with single accepted outcome."""
        outcomes = [{"status": "accepted_for_validation", "path": "src/auth.py"}]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 1
        assert result["dropped_candidate_count"] == 0
        assert result["accepted_for_validation_count"] == 1

    def test_single_outcome_dropped(self) -> None:
        """Test aggregation with single dropped outcome."""
        outcomes = [{"status": "dropped_non_business_surface", "path": "tests/test.py"}]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 1
        assert result["dropped_candidate_count"] == 1
        assert result["accepted_for_validation_count"] == 0

    def test_all_technical_artifacts(self) -> None:
        """Test aggregation with all technical artifact drops."""
        outcomes = [
            {"status": "dropped_technical_artifact", "path": "src/__init__.py"},
            {"status": "dropped_technical_artifact", "path": "src/helpers.py"},
            {"status": "dropped_technical_artifact", "path": "fixtures/data.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 3
        assert result["dropped_candidate_count"] == 3
        assert result["dropped_technical_artifact_count"] == 3

    def test_all_missing_anchor(self) -> None:
        """Test aggregation with all missing enforcement anchors."""
        outcomes = [
            {"status": "dropped_missing_enforcement_anchor", "path": "src/comment1.py"},
            {"status": "dropped_missing_enforcement_anchor", "path": "src/comment2.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 2
        assert result["dropped_missing_enforcement_anchor_count"] == 2

    def test_all_missing_business_semantics(self) -> None:
        """Test aggregation with all missing business semantics."""
        outcomes = [
            {"status": "dropped_missing_business_semantics", "path": "src/generic.py"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 1
        assert result["dropped_missing_business_semantics_count"] == 1


class TestAggregateDiscoveryOutcomeCountsEdgeCases:
    """Edge case tests for outcome aggregation."""

    def test_very_large_outcome_list(self) -> None:
        """Test aggregation with very large outcome list (edge case)."""
        # Create 10000 outcomes
        outcomes = []
        for i in range(5000):
            outcomes.append({"status": "accepted_for_validation", "path": f"src/valid_{i}.py"})
        for i in range(3000):
            outcomes.append({"status": "dropped_non_business_surface", "path": f"tests/test_{i}.py"})
        for i in range(2000):
            outcomes.append({"status": "dropped_schema_only", "path": f"config/schema_{i}.yaml"})
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 10000
        assert result["accepted_for_validation_count"] == 5000
        assert result["dropped_non_business_surface_count"] == 3000
        assert result["dropped_schema_only_count"] == 2000

    def test_all_status_types_together(self) -> None:
        """Test aggregation with all possible status types."""
        outcomes = [
            {"status": "accepted_for_validation"},
            {"status": "dropped_non_business_surface"},
            {"status": "dropped_schema_only"},
            {"status": "dropped_non_executable_normative_text"},
            {"status": "dropped_technical_artifact"},
            {"status": "dropped_missing_enforcement_anchor"},
            {"status": "dropped_missing_business_semantics"},
        ]
        
        result = _aggregate_discovery_outcome_counts(outcomes)
        
        assert result["raw_candidate_count"] == 7
        assert result["dropped_candidate_count"] == 6
        assert result["accepted_for_validation_count"] == 1
        assert result["dropped_non_business_surface_count"] == 1
        assert result["dropped_schema_only_count"] == 1
        assert result["dropped_non_executable_normative_text_count"] == 1
        assert result["dropped_technical_artifact_count"] == 1
        assert result["dropped_missing_enforcement_anchor_count"] == 1
        assert result["dropped_missing_business_semantics_count"] == 1


class TestBuildCodeExtractionCountersWithOutcomes:
    """Tests for _build_code_extraction_counters using aggregated outcomes."""

    def test_counts_from_discovery_outcomes(self) -> None:
        """Test that counters are built from discovery_outcomes."""
        report_map = {
            "discovery_outcomes": [
                {"status": "accepted_for_validation", "path": "src/auth.py"},
                {"status": "accepted_for_validation", "path": "src/validation.py"},
                {"status": "dropped_non_business_surface", "path": "tests/test_auth.py"},
                {"status": "dropped_schema_only", "path": "config/schema.yaml"},
            ]
        }
        
        counters = _build_code_extraction_counters(report_map)
        
        assert counters.raw_candidate_count == 4
        assert counters.candidate_count == 2  # accepted
        assert counters.dropped_candidate_count == 2
        assert counters.dropped_non_business_surface_count == 1
        assert counters.dropped_schema_only_count == 1
        assert counters.accepted_business_enforcement_count == 2

    def test_explicit_values_override_aggregated(self) -> None:
        """Test that explicit values in report_map override aggregated when NO discovery_outcomes.
        
        When discovery_outcomes IS present, aggregated counts take SSOT precedence.
        """
        # Without discovery_outcomes, report_map values should be used
        report_map = {
            "dropped_non_business_surface_count": 99,
        }
        
        counters = _build_code_extraction_counters(report_map)
        
        # When no discovery_outcomes, report_map values are used
        assert counters.dropped_non_business_surface_count == 99

    def test_empty_discovery_outcomes(self) -> None:
        """Test counters with empty discovery_outcomes."""
        report_map = {"discovery_outcomes": []}
        
        counters = _build_code_extraction_counters(report_map)
        
        assert counters.raw_candidate_count == 0
        assert counters.dropped_non_business_surface_count == 0

    def test_missing_discovery_outcomes(self) -> None:
        """Test counters when discovery_outcomes is missing."""
        report_map = {}
        
        counters = _build_code_extraction_counters(report_map)
        
        # Should use defaults (0) when no outcomes provided
        assert counters.raw_candidate_count == 0


class TestCodeExtractionCountersInvariant:
    """Tests for CodeExtractionCounters invariant checks."""

    def test_valid_invariant(self) -> None:
        """Test that valid counters pass invariant check."""
        counters = CodeExtractionCounters(
            raw_candidate_count=10,
            dropped_candidate_count=6,
            candidate_count=4,
            validated_code_rule_count=3,
            invalid_code_candidate_count=1,
        )
        
        assert counters.raw_candidate_count == 10
        assert counters.candidate_count == 4

    def test_invalid_invariant_raw_equals_dropped_plus_candidate(self) -> None:
        """Test that invariant is checked for raw = dropped + candidate.
        
        The hard invariant check is now enforced - this test verifies that
        invalid combinations raise ValueError.
        """
        # This should raise because raw != dropped + candidate
        with pytest.raises(ValueError, match="dropped_candidate_count"):
            CodeExtractionCounters(
                raw_candidate_count=10,
                dropped_candidate_count=3,
                candidate_count=4,  # 3 + 4 = 7 != 10
                validated_code_rule_count=3,
                invalid_code_candidate_count=1,
            )

    def test_diagnostic_counts_accessible(self) -> None:
        """Test that diagnostic counts are accessible."""
        counters = CodeExtractionCounters(
            raw_candidate_count=10,
            dropped_candidate_count=6,
            candidate_count=4,
            validated_code_rule_count=3,
            invalid_code_candidate_count=1,
            dropped_non_business_surface_count=2,
            dropped_schema_only_count=1,
            accepted_business_enforcement_count=3,
        )
        
        assert counters.dropped_non_business_surface_count == 2
        assert counters.dropped_schema_only_count == 1
        assert counters.accepted_business_enforcement_count == 3


class TestCounterRoundtripIntegration:
    """Integration tests for counter roundtrip between extraction and hydration."""

    def test_full_roundtrip_with_all_categories(self) -> None:
        """Test complete roundtrip from discovery outcomes to counters."""
        # Simulate discovery outcomes from extraction
        discovery_outcomes = [
            {"status": "accepted_for_validation", "path": "src/auth.py", "evidence_kind": "executable_code"},
            {"status": "accepted_for_validation", "path": "src/validation.py", "evidence_kind": "executable_code"},
            {"status": "accepted_for_validation", "path": "src/workflow.py", "evidence_kind": "executable_code"},
            {"status": "dropped_non_business_surface", "path": "tests/test_auth.py", "evidence_kind": "test"},
            {"status": "dropped_schema_only", "path": "schemas/rules.yaml", "evidence_kind": "schema"},
            {"status": "dropped_non_executable_normative_text", "path": "docs/policy.md", "evidence_kind": "docstring"},
            {"status": "dropped_technical_artifact", "path": "src/__init__.py", "evidence_kind": "infra"},
            {"status": "dropped_missing_enforcement_anchor", "path": "src/broken.py", "evidence_kind": "other"},
        ]
        
        # First: aggregate from outcomes
        aggregated = _aggregate_discovery_outcome_counts(discovery_outcomes)
        
        assert aggregated["raw_candidate_count"] == 8
        assert aggregated["accepted_for_validation_count"] == 3
        assert aggregated["dropped_non_business_surface_count"] == 1
        assert aggregated["dropped_schema_only_count"] == 1
        
        # Second: build counters from report_map with outcomes
        report_map = {"discovery_outcomes": discovery_outcomes}
        counters = _build_code_extraction_counters(report_map)
        
        # Verify SSOT: counts match aggregated values
        assert counters.raw_candidate_count == aggregated["raw_candidate_count"]
        assert counters.dropped_non_business_surface_count == aggregated["dropped_non_business_surface_count"]
        assert counters.dropped_schema_only_count == aggregated["dropped_schema_only_count"]
        assert counters.accepted_business_enforcement_count == aggregated["accepted_for_validation_count"]

    def test_governance_repo_fixture_counts(self) -> None:
        """Test with typical governance repo fixture - should have drops."""
        # Typical governance repo has many non-business-surface files
        discovery_outcomes = [
            {"status": "accepted_for_validation", "path": "src/validators.py"},
            {"status": "dropped_non_business_surface", "path": "tests/test_validators.py"},
            {"status": "dropped_non_business_surface", "path": ".github/workflows/ci.yaml"},
            {"status": "dropped_non_business_surface", "path": "docs/architecture.md"},
            {"status": "dropped_schema_only", "path": "schemas/schema.yaml"},
            {"status": "dropped_technical_artifact", "path": "src/__init__.py"},
        ]
        
        aggregated = _aggregate_discovery_outcome_counts(discovery_outcomes)
        
        # Governance repo should have non-zero drops
        assert aggregated["dropped_non_business_surface_count"] > 0
        assert aggregated["raw_candidate_count"] > aggregated["accepted_for_validation_count"]

    def test_schema_fixture_counts(self) -> None:
        """Test with schema-only fixture - should have schema drops."""
        discovery_outcomes = [
            {"status": "accepted_for_validation", "path": "src/validation.py"},
            {"status": "dropped_schema_only", "path": "schemas/user.json"},
            {"status": "dropped_schema_only", "path": "schemas/order.json"},
        ]
        
        aggregated = _aggregate_discovery_outcome_counts(discovery_outcomes)
        
        # Schema fixture should have schema drops
        assert aggregated["dropped_schema_only_count"] > 0

    def test_generic_subject_fixture_counts(self) -> None:
        """Test with generic subject fixture - should have drops."""
        discovery_outcomes = [
            {"status": "accepted_for_validation", "path": "src/customer_validation.py"},
            {"status": "dropped_non_business_surface", "path": "tests/test_customer.py"},
            {"status": "dropped_missing_business_semantics", "path": "src/generic_handler.py"},
        ]
        
        aggregated = _aggregate_discovery_outcome_counts(discovery_outcomes)
        
        # Should have drops due to missing business context
        assert aggregated["dropped_candidate_count"] > 0
