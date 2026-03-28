"""Tests for ResponseValidator subsystem."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_runtime.application.services.phase6_review_orchestrator.response_validator import (
    ResponseValidator,
    ValidationResult,
)


_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_schema() -> dict | None:
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


class TestResponseValidator:
    """Tests for ResponseValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a ResponseValidator instance."""
        return ResponseValidator()

    def test_validate_empty_response(self, validator):
        """Empty response returns invalid with changes_requested."""
        result = validator.validate("")
        assert result.valid is False
        assert result.verdict == "changes_requested"
        assert "empty response" in result.findings[0].lower()

    def test_validate_whitespace_only_response(self, validator):
        """Whitespace-only response returns invalid."""
        result = validator.validate("   \n  ")
        assert result.valid is False

    def test_validate_non_json_response(self, validator):
        """Non-JSON response returns invalid."""
        result = validator.validate("This is not JSON")
        assert result.valid is False
        assert "response-not-structured-json" in result.violations

    def test_validate_malformed_json(self, validator):
        """Malformed JSON returns invalid."""
        result = validator.validate("{invalid json")
        assert result.valid is False

    def test_validate_valid_json_approve(self, validator):
        """Valid JSON with approve verdict returns valid."""
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "All checks passed",
            "contract_check": "No drift",
            "findings": [],
            "regression_assessment": "Low risk",
            "test_assessment": "Sufficient",
        })
        result = validator.validate(response, mandates_schema=None)
        assert result.valid is True
        assert result.verdict == "approve"
        assert result.is_approve is True

    def test_validate_valid_json_changes_requested(self, validator):
        """Valid JSON with changes_requested verdict returns valid."""
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Issues found during review",
            "contract_check": "Minor drift detected",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/foo.py:42",
                    "evidence": "Bug discovered in critical path here",
                    "impact": "Could crash the application",
                    "fix": "Fix it properly",
                }
            ],
            "regression_assessment": "Medium risk assessment",
            "test_assessment": "Insufficient coverage",
        })
        result = validator.validate(response, mandates_schema=None)
        assert result.valid is True
        assert result.verdict == "changes_requested"
        assert result.is_changes_requested is True
        assert len(result.findings) == 1
        assert "high" in result.findings[0]
        assert "src/foo.py:42" in result.findings[0]

    def test_edge_coerces_findings_when_json_array_string(self, validator):
        """Stringified findings array is normalized before schema validation."""
        schema = _load_schema()
        if not isinstance(schema, dict):
            pytest.skip("mandates schema not available")

        finding = {
            "severity": "high",
            "type": "defect",
            "location": "src/foo.py:42",
            "evidence": "Bug discovered in critical path here",
            "impact": "Could crash the application",
            "fix": "Fix it properly",
        }
        response = json.dumps(
            {
                "verdict": "changes_requested",
                "governing_evidence": "Issues found during review",
                "contract_check": "Minor drift detected",
                "findings": json.dumps([finding], ensure_ascii=True),
                "regression_assessment": "Medium risk assessment",
                "test_assessment": "Insufficient coverage",
            },
            ensure_ascii=True,
        )
        result = validator.validate(response, mandates_schema=schema)
        assert result.valid is True
        assert result.verdict == "changes_requested"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_is_approve_true_when_valid_approve(self):
        """is_approve returns True for valid approve."""
        result = ValidationResult(
            valid=True,
            verdict="approve",
            findings=[],
            violations=[],
        )
        assert result.is_approve is True

    def test_is_approve_false_when_invalid(self):
        """is_approve returns False when invalid."""
        result = ValidationResult(
            valid=False,
            verdict="approve",
            findings=[],
            violations=["error"],
        )
        assert result.is_approve is False

    def test_is_changes_requested_true(self):
        """is_changes_requested returns True for changes_requested verdict."""
        result = ValidationResult(
            valid=True,
            verdict="changes_requested",
            findings=[],
            violations=[],
        )
        assert result.is_changes_requested is True

    def test_is_changes_requested_false_for_approve(self):
        """is_changes_requested returns False for approve verdict."""
        result = ValidationResult(
            valid=True,
            verdict="approve",
            findings=[],
            violations=[],
        )
        assert result.is_changes_requested is False
