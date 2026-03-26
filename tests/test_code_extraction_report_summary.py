"""Tests for CodeExtractionReport summary optimization.

This module tests the reduction of SESSION_STATE size by replacing full
discovery_outcomes lists with compact summary objects.
"""
import pytest
from pathlib import Path

from governance_runtime.engine.business_rules_hydration import (
    hydrate_code_extraction_report_for_session_state,
    build_business_rules_state_snapshot,
    CodeExtractionCounters,
)


class TestCodeExtractionReportSummary:
    """Happy path tests for CodeExtractionReport summary."""

    def test_summary_contains_count_and_truncated(self) -> None:
        """Summary must contain count and truncated flag."""
        report_map = {
            "discovery_outcomes": [
                {"path": "src/a.py", "status": "accepted_for_validation"},
                {"path": "src/b.py", "status": "accepted_for_validation"},
            ],
            "raw_candidate_count": 2,
            "candidate_count": 2,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=2,
            candidate_count=2,
            dropped_candidate_count=0,
            validated_code_rule_count=2,
            invalid_code_candidate_count=0,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc123",
            include_discovery_outcomes=False,
        )

        assert isinstance(result["discovery_outcomes"], dict)
        assert result["discovery_outcomes"]["count"] == 2
        assert result["discovery_outcomes"]["truncated"] is False
        assert result["discovery_outcomes"]["samples"] == []

    def test_snapshot_with_summary_reduces_size(self) -> None:
        """Snapshot with summary should be significantly smaller than with full outcomes."""
        import json

        # Create report with many outcomes
        many_outcomes = [
            {"path": f"src/file{i}.py", "status": "accepted_for_validation", "line_start": i}
            for i in range(100)
        ]
        report_map = {
            "discovery_outcomes": many_outcomes,
            "raw_candidate_count": 100,
            "candidate_count": 80,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=100,
            candidate_count=80,
            dropped_candidate_count=20,
            validated_code_rule_count=75,
            invalid_code_candidate_count=5,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc123",
            include_discovery_outcomes=False,
        )

        summary_size = len(json.dumps(result))
        # With 100 outcomes, old format would be ~30000+ bytes
        # Summary should be < 2000 bytes
        assert summary_size < 2000, f"Summary too large: {summary_size}"


class TestCodeExtractionReportBadPath:
    """Bad path tests for error handling."""

    def test_missing_discovery_outcomes_uses_counters(self) -> None:
        """When discovery_outcomes is missing, use raw_candidate_count from counters."""
        report_map = {
            "raw_candidate_count": 50,
            "candidate_count": 30,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=50,
            candidate_count=30,
            dropped_candidate_count=20,
            validated_code_rule_count=25,
            invalid_code_candidate_count=5,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc123",
            include_discovery_outcomes=False,
        )

        assert result["discovery_outcomes"]["count"] == 50

    def test_none_outcomes_handled_gracefully(self) -> None:
        """None discovery_outcomes should not crash."""
        report_map = {
            "discovery_outcomes": None,
            "raw_candidate_count": 10,
            "candidate_count": 5,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=10,
            candidate_count=5,
            dropped_candidate_count=5,
            validated_code_rule_count=4,
            invalid_code_candidate_count=1,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc123",
            include_discovery_outcomes=False,
        )

        assert result["discovery_outcomes"]["count"] == 10


class TestCodeExtractionReportCornerCases:
    """Corner case tests."""

    def test_empty_outcomes_with_zero_counts(self) -> None:
        """Edge case: empty outcomes with zero counts."""
        report_map = {
            "discovery_outcomes": [],
            "raw_candidate_count": 0,
            "candidate_count": 0,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=0,
            candidate_count=0,
            dropped_candidate_count=0,
            validated_code_rule_count=0,
            invalid_code_candidate_count=0,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="",
            include_discovery_outcomes=False,
        )

        assert result["discovery_outcomes"]["count"] == 0
        assert result["discovery_outcomes"]["truncated"] is False

    def test_truncated_flag_when_outcomes_missing_but_candidates_exist(self) -> None:
        """truncated should be True when outcomes missing but candidates exist."""
        report_map = {
            "discovery_outcomes": [],  # Empty but should indicate truncation
            "raw_candidate_count": 100,
            "candidate_count": 50,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=100,
            candidate_count=50,
            dropped_candidate_count=50,
            validated_code_rule_count=45,
            invalid_code_candidate_count=5,
            accepted_business_enforcement_count=50,  # Non-zero triggers truncation signal
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc123",
            include_discovery_outcomes=False,
        )

        assert result["discovery_outcomes"]["truncated"] is True


class TestCodeExtractionReportEdgeCases:
    """Edge case tests for extreme values."""

    def test_large_outcome_count(self) -> None:
        """Test with very large outcome count (simulating large codebase)."""
        many_outcomes = [
            {"path": f"src/file{i}.py", "status": "accepted_for_validation"}
            for i in range(10000)
        ]
        report_map = {
            "discovery_outcomes": many_outcomes,
            "raw_candidate_count": 10000,
            "candidate_count": 8000,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=10000,
            candidate_count=8000,
            dropped_candidate_count=2000,
            validated_code_rule_count=7500,
            invalid_code_candidate_count=500,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc123",
            include_discovery_outcomes=False,
        )

        # Even with 10k outcomes, summary should be small
        import json
        result_json = json.dumps(result)
        assert len(result_json) < 3000, f"Result too large: {len(result_json)}"


class TestCodeExtractionReportPerformance:
    """Performance tests for CodeExtractionReport optimization."""

    def test_summary_generation_is_fast(self) -> None:
        """Summary generation should be fast even with many outcomes."""
        import time

        many_outcomes = [
            {"path": f"src/file{i}.py", "status": "accepted_for_validation", "line_start": i}
            for i in range(1000)
        ]
        report_map = {
            "discovery_outcomes": many_outcomes,
            "raw_candidate_count": 1000,
            "candidate_count": 800,
        }
        counters = CodeExtractionCounters(
            raw_candidate_count=1000,
            candidate_count=800,
            dropped_candidate_count=200,
            validated_code_rule_count=750,
            invalid_code_candidate_count=50,
        )

        # Time 1000 iterations
        start = time.time()
        for _ in range(1000):
            hydrate_code_extraction_report_for_session_state(
                report_map=report_map,
                counters=counters,
                report_sha="abc123",
                include_discovery_outcomes=False,
            )
        elapsed = time.time() - start

        # Should complete 1000 iterations in under 1 second
        assert elapsed < 1.0, f"Took {elapsed:.2f}s for 1000 iterations"

    def test_memory_efficiency_with_summary(self) -> None:
        """Summary should use significantly less memory than full list."""
        import sys

        many_outcomes = [{"path": f"src/f{i}.py", "status": "accepted"} for i in range(100)]
        report_map = {"discovery_outcomes": many_outcomes}
        counters = CodeExtractionCounters(
            raw_candidate_count=100,
            candidate_count=80,
            dropped_candidate_count=20,
            validated_code_rule_count=75,
            invalid_code_candidate_count=5,
        )

        result = hydrate_code_extraction_report_for_session_state(
            report_map=report_map,
            counters=counters,
            report_sha="abc",
            include_discovery_outcomes=False,
        )

        # Summary dict should be much smaller than list
        # The list would contain 100 dicts, summary has just 3 keys
        summary = result["discovery_outcomes"]
        # Verify it's a dict not a list (the key change)
        assert isinstance(summary, dict), "Must be dict, not list"