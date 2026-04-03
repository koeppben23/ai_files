"""Response validator for Phase-6 LLM review.

Validates LLM responses against the governance mandates schema.
This component is responsible for:
- Parsing JSON responses
- Validating against the review output schema
- Extracting findings and verdict

All validation is fail-closed: invalid responses are rejected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating an LLM response."""

    valid: bool
    verdict: str  # "approve", "changes_requested", "unknown"
    findings: list[str]
    violations: list[str]  # Schema violation rules
    parsed_data: dict[str, Any] | None = None
    raw_response: str | None = None

    @property
    def is_approve(self) -> bool:
        """Check if the verdict is approve."""
        return self.valid and self.verdict == "approve"

    @property
    def is_changes_requested(self) -> bool:
        """Check if the verdict is changes_requested."""
        return self.verdict == "changes_requested"


class ResponseValidator:
    """Validates LLM review responses against the schema.

    This component encapsulates all response validation logic.
    It does NOT execute LLM calls - that's the LLMCaller's job.
    """

    def __init__(self, *, validators_path: Path | None = None) -> None:
        """Initialize the response validator.

        Args:
            validators_path: Path to the validators directory.
                            If None, uses default location.
        """
        self._validate_func, self._coerce_func = self._load_validator(validators_path)

    def _load_validator(self, validators_path: Path | None = None):
        """Load the llm_response_validator module."""
        if validators_path is None:
            # From: governance_runtime/application/services/phase6_review_orchestrator/response_validator.py
            # To:   governance_runtime/application/validators
            validators_dir = Path(__file__).parent.parent.parent / "validators"
        else:
            validators_dir = validators_path

        import sys

        if str(validators_dir) not in sys.path:
            sys.path.insert(0, str(validators_dir))
        try:
            from llm_response_validator import (
                coerce_output_against_mandates_schema,
                validate_review_response,
            )

            return validate_review_response, coerce_output_against_mandates_schema
        except (ImportError, AttributeError):
            return None, None

    def validate(
        self,
        response_text: str,
        mandates_schema: dict[str, object] | None = None,
    ) -> ValidationResult:
        """Validate an LLM review response.

        Args:
            response_text: The raw response text from the LLM.
            mandates_schema: The loaded mandates schema for validation.

        Returns:
            ValidationResult with validation outcome.
        """
        raw_text = response_text.strip()

        if not raw_text:
            return ValidationResult(
                valid=False,
                verdict="changes_requested",
                findings=["LLM returned empty response"],
                violations=["response-not-structured-json"],
                raw_response="",
            )

        # Try to parse JSON
        parsed_data: dict[str, Any] | None = None
        if raw_text.startswith("{"):
            try:
                parsed_data = json.loads(raw_text)
            except json.JSONDecodeError:
                pass

        if parsed_data is None:
            snippet = raw_text[:80] if len(raw_text) > 80 else raw_text
            return ValidationResult(
                valid=False,
                verdict="changes_requested",
                findings=[
                    f"response-not-structured-json: LLM did not return valid JSON. "
                    f"Received {len(raw_text)} chars starting with: {snippet!r}"
                ],
                violations=["response-not-structured-json"],
                raw_response=raw_text[:1000],
            )

        # Check if validator is available
        if self._validate_func is None:
            return ValidationResult(
                valid=False,
                verdict="changes_requested",
                findings=["validator-not-available: llm_response_validator could not be imported"],
                violations=["validator-not-available"],
                raw_response=raw_text[:1000],
            )

        if self._coerce_func is not None:
            normalized = self._coerce_func(parsed_data, mandates_schema, "reviewOutputSchema")
            if isinstance(normalized, dict):
                parsed_data = normalized

        # Run schema validation
        validation = self._validate_func(parsed_data, mandates_schema=mandates_schema)
        if not validation.valid:
            violations = [v.rule for v in validation.violations]
            findings = [f"schema-violation: {v.rule}" for v in validation.violations]
            return ValidationResult(
                valid=False,
                verdict="changes_requested",
                findings=findings,
                violations=violations,
                raw_response=raw_text[:1000],
            )

        # Extract findings from response
        findings: list[str] = []
        for f in parsed_data.get("findings", []) or []:
            if isinstance(f, dict):
                severity = f.get("severity", "?")
                location = f.get("location", "?")
                evidence = f.get("evidence", "")
                findings.append(f"[{severity}] {location}: {evidence[:100]}")

        return ValidationResult(
            valid=True,
            verdict=parsed_data.get("verdict", "changes_requested"),
            findings=findings,
            violations=[],
            parsed_data=parsed_data,
            raw_response=raw_text[:1000],
        )
