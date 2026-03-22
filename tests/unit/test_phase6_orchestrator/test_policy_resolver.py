"""Tests for PolicyResolver subsystem."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_runtime.application.services.phase6_review_orchestrator.policy_resolver import (
    PolicyResolver,
    BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
)


class TestPolicyResolver:
    """Tests for PolicyResolver class."""

    @pytest.fixture
    def resolver(self):
        """Create a PolicyResolver instance."""
        return PolicyResolver()

    @pytest.fixture
    def resolver_with_schema(self, tmp_path):
        """Create a PolicyResolver with a mock schema."""
        schema = {
            "$defs": {
                "reviewOutputSchema": {
                    "type": "object",
                    "properties": {
                        "verdict": {"type": "string"},
                    },
                }
            },
            "review_mandate": {
                "role": "Senior Reviewer",
                "core_posture": ["Thorough", "Precise"],
                "evidence_rule": ["Review all code"],
                "review_lenses": [
                    {
                        "name": "Security Lens",
                        "body": ["Check for vulnerabilities"],
                        "ask": ["Is this secure?"],
                    }
                ],
                "decision_rules": ["Must pass all checks"],
            },
        }
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(json.dumps(schema))
        return PolicyResolver(schema_path=schema_path)

    def test_load_mandate_schema_returns_none_when_not_found(self, resolver):
        """load_mandate_schema returns None when schema file doesn't exist."""
        resolver._schema_path = Path("/nonexistent/schema.json")
        result = resolver.load_mandate_schema()
        assert result is None

    def test_load_mandate_schema_returns_schema_when_found(self, resolver_with_schema):
        """load_mandate_schema returns MandateSchema when schema exists."""
        result = resolver_with_schema.load_mandate_schema()
        assert result is not None
        assert "reviewOutputSchema" in result.raw_schema.get("$defs", {})

    def test_extract_review_output_schema_text(self, resolver_with_schema):
        """_extract_review_output_schema returns JSON text of reviewOutputSchema."""
        result = resolver_with_schema.load_mandate_schema()
        assert result is not None
        schema_text = result.review_output_schema_text
        assert "verdict" in schema_text
        parsed = json.loads(schema_text)
        assert parsed["type"] == "object"

    def test_build_mandate_text(self, resolver_with_schema):
        """_build_mandate_text returns formatted mandate text."""
        result = resolver_with_schema.load_mandate_schema()
        assert result is not None
        mandate_text = result.mandate_text
        assert "Role: Senior Reviewer" in mandate_text
        assert "Thorough" in mandate_text
        assert "Security Lens" in mandate_text
        assert "Must pass all checks" in mandate_text

    def test_load_effective_review_policy_returns_error_when_no_rulebooks(self, resolver):
        """load_effective_review_policy returns error when no LoadedRulebooks."""
        result = resolver.load_effective_review_policy(
            state={"SESSION_STATE": {}},
            commands_home=Path("/tmp"),
        )
        assert result.is_available is False
        assert result.error_code == BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE


class TestPolicyResolverMandateBuilding:
    """Tests for mandate text building."""

    def test_empty_mandate_returns_empty_string(self):
        """Empty mandate dict returns empty string."""
        resolver = PolicyResolver()
        result = resolver._build_mandate_text({"review_mandate": {}})
        assert result == ""

    def test_mandate_with_role_only(self):
        """Mandate with only role returns role line."""
        resolver = PolicyResolver()
        result = resolver._build_mandate_text({"review_mandate": {"role": "Reviewer"}})
        assert result == "Role: Reviewer"

    def test_mandate_with_posture(self):
        """Mandate with core_posture returns bullet list."""
        resolver = PolicyResolver()
        result = resolver._build_mandate_text({
            "review_mandate": {
                "role": "Reviewer",
                "core_posture": ["Thorough", "Precise"],
            }
        })
        assert "Role: Reviewer" in result
        assert "- Thorough" in result
        assert "- Precise" in result
