"""Tests for BusinessRuleCandidates schema in CodebaseContext.

Validates that the JSON Schema and embedded Python schema correctly accept
valid BusinessRuleCandidates structures and reject invalid ones.
Covers: Happy, Bad, Corner, Edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.engine.schema_validator import validate_against_schema
from governance.engine._embedded_session_state_schema import (
    SESSION_STATE_CORE_SCHEMA,
    _HARDCODED_FALLBACK_SCHEMA,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_session_with_codebase_context(candidates: object | None = None) -> dict:
    """Build a minimal valid SESSION_STATE with CodebaseContext."""
    ctx: dict[str, object] = {
        "ExistingAbstractions": [],
        "DependencyGraph": [],
        "PatternFingerprint": {},
        "TechnicalDebtMarkers": [],
    }
    if candidates is not None:
        ctx["BusinessRuleCandidates"] = candidates
    return {
        "SESSION_STATE": {
            "session_state_version": 1,
            "ruleset_hash": "abc123",
            "Phase": "2",
            "Mode": "NORMAL",
            "OutputMode": "ARCHITECT",
            "ConfidenceLevel": 85,
            "Next": "Continue",
            "Bootstrap": {"Present": True, "Satisfied": True, "Evidence": "test"},
            "Scope": {},
            "RepoFacts": {},
            "LoadedRulebooks": {},
            "AddonsEvidence": {},
            "RulebookLoadEvidence": {},
            "ActiveProfile": None,
            "ProfileSource": None,
            "ProfileEvidence": None,
            "Gates": {},
            "DecisionSurface": {},
            "CodebaseContext": ctx,
        }
    }


def _valid_candidate(**overrides: object) -> dict:
    """Return a single valid BusinessRuleCandidate dict."""
    base: dict[str, object] = {
        "id": "BR-C001",
        "candidate_rule_text": "BR-C001: Withdrawal amount must not exceed the daily limit",
        "source_path": "src/main/java/com/bank/WithdrawalService.java",
        "line_range": "42-48",
        "pattern_type": "validation-guard",
        "confidence": "high",
        "evidence_snippet": "if (amount > MAX_DAILY) throw new PolicyException(...)",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Schemas under test — both embedded and JSON-file
# ---------------------------------------------------------------------------

@pytest.fixture(params=["embedded", "json_file"], ids=["embedded", "json_file"])
def schema(request: pytest.FixtureRequest) -> dict:
    if request.param == "embedded":
        return SESSION_STATE_CORE_SCHEMA
    repo_root = Path(__file__).resolve().parents[1]
    json_path = repo_root / "governance" / "assets" / "schemas" / "session_state.core.v1.schema.json"
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# Happy-path tests
# ===========================================================================

@pytest.mark.governance
class TestBusinessRuleCandidatesHappy:
    """Valid structures that MUST pass schema validation."""

    def test_single_valid_candidate(self, schema: dict) -> None:
        doc = _minimal_session_with_codebase_context([_valid_candidate()])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_multiple_valid_candidates(self, schema: dict) -> None:
        candidates = [
            _valid_candidate(id="BR-C001"),
            _valid_candidate(
                id="BR-C002",
                candidate_rule_text="BR-C002: Order status must be PENDING before approval",
                pattern_type="enum-invariant",
                confidence="medium",
            ),
            _valid_candidate(
                id="BR-C003",
                candidate_rule_text="BR-C003: Account holder name is required for all transfers",
                pattern_type="constraint-check",
            ),
        ]
        doc = _minimal_session_with_codebase_context(candidates)
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_empty_array_signals_scan_performed(self, schema: dict) -> None:
        """Empty array = 'scan performed, nothing found' — MUST be valid."""
        doc = _minimal_session_with_codebase_context([])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_field_omitted_signals_scan_not_performed(self, schema: dict) -> None:
        """Omitted field = 'scan not performed' — MUST be valid (CodebaseContext has additionalProperties: true)."""
        doc = _minimal_session_with_codebase_context(None)
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_all_pattern_types_accepted(self, schema: dict) -> None:
        """Every enum value in pattern_type must be valid."""
        valid_types = [
            "validation-guard",
            "constraint-check",
            "policy-enforcement",
            "enum-invariant",
            "schema-constraint",
            "guard-clause",
            "config-rule",
        ]
        for pt in valid_types:
            doc = _minimal_session_with_codebase_context([_valid_candidate(pattern_type=pt)])
            errors = validate_against_schema(schema=schema, value=doc)
            assert not any("pattern_type" in e for e in errors), f"pattern_type={pt} rejected"

    def test_both_confidence_levels_accepted(self, schema: dict) -> None:
        for conf in ("high", "medium"):
            doc = _minimal_session_with_codebase_context(
                [_valid_candidate(confidence=conf)]
            )
            errors = validate_against_schema(schema=schema, value=doc)
            assert not any("confidence" in e for e in errors), f"confidence={conf} rejected"

    def test_evidence_snippet_optional(self, schema: dict) -> None:
        """evidence_snippet is not required — candidate without it must be valid."""
        c = _valid_candidate()
        del c["evidence_snippet"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_line_range_optional(self, schema: dict) -> None:
        """line_range is not required — candidate without it must be valid."""
        c = _valid_candidate()
        del c["line_range"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)


# ===========================================================================
# Bad-input tests
# ===========================================================================

@pytest.mark.governance
class TestBusinessRuleCandidatesBad:
    """Invalid structures that MUST fail schema validation."""

    def test_missing_required_id(self, schema: dict) -> None:
        c = _valid_candidate()
        del c["id"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("id:required" in e for e in errors)

    def test_missing_required_candidate_rule_text(self, schema: dict) -> None:
        c = _valid_candidate()
        del c["candidate_rule_text"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("candidate_rule_text:required" in e for e in errors)

    def test_missing_required_source_path(self, schema: dict) -> None:
        c = _valid_candidate()
        del c["source_path"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("source_path:required" in e for e in errors)

    def test_missing_required_pattern_type(self, schema: dict) -> None:
        c = _valid_candidate()
        del c["pattern_type"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("pattern_type:required" in e for e in errors)

    def test_missing_required_confidence(self, schema: dict) -> None:
        c = _valid_candidate()
        del c["confidence"]
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("confidence:required" in e for e in errors)

    def test_invalid_pattern_type_enum(self, schema: dict) -> None:
        c = _valid_candidate(pattern_type="not-a-real-type")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("pattern_type:enum" in e for e in errors)

    def test_invalid_confidence_enum(self, schema: dict) -> None:
        c = _valid_candidate(confidence="low")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("confidence:enum" in e for e in errors)

    def test_id_wrong_pattern_no_prefix(self, schema: dict) -> None:
        """ID must match ^BR-C\\d{3,}$ — missing BR-C prefix."""
        c = _valid_candidate(id="BR-001")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("id:pattern" in e for e in errors)

    def test_id_wrong_pattern_too_few_digits(self, schema: dict) -> None:
        """ID must have at least 3 digits after BR-C."""
        c = _valid_candidate(id="BR-C01")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("id:pattern" in e for e in errors)

    def test_additional_properties_rejected(self, schema: dict) -> None:
        """Candidate items have additionalProperties: false."""
        c = _valid_candidate()
        c["extra_field"] = "should be rejected"
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("extra_field:unexpected" in e for e in errors)

    def test_candidates_not_array(self, schema: dict) -> None:
        """BusinessRuleCandidates must be an array, not an object."""
        doc = _minimal_session_with_codebase_context({"not": "an array"})
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("BusinessRuleCandidates" in e and "array" in e for e in errors)


# ===========================================================================
# Corner-case tests
# ===========================================================================

@pytest.mark.governance
class TestBusinessRuleCandidatesCorner:
    """Edge conditions around boundaries and unusual but valid inputs."""

    def test_id_exactly_three_digits(self, schema: dict) -> None:
        """BR-C001 (minimum digits) must be accepted."""
        c = _valid_candidate(id="BR-C001")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("id" in e for e in errors)

    def test_id_many_digits(self, schema: dict) -> None:
        """BR-C00001 (5 digits) must still be accepted."""
        c = _valid_candidate(id="BR-C00001")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("id" in e for e in errors)

    def test_evidence_snippet_at_max_length(self, schema: dict) -> None:
        """Exactly 500 chars must be accepted."""
        c = _valid_candidate(evidence_snippet="x" * 500)
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("evidence_snippet:maxLength" in e for e in errors)

    def test_evidence_snippet_exceeds_max_length(self, schema: dict) -> None:
        """501 chars must be rejected."""
        c = _valid_candidate(evidence_snippet="x" * 501)
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("evidence_snippet:maxLength" in e for e in errors)

    def test_candidate_with_empty_strings_for_optional_fields(self, schema: dict) -> None:
        """Empty strings in optional fields (line_range, evidence_snippet) — valid per schema."""
        c = _valid_candidate(line_range="", evidence_snippet="")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_codebase_context_with_candidates_and_all_other_fields(self, schema: dict) -> None:
        """Full CodebaseContext with all fields including candidates — must pass."""
        doc = _minimal_session_with_codebase_context([_valid_candidate()])
        ctx = doc["SESSION_STATE"]["CodebaseContext"]  # type: ignore[index]
        assert isinstance(ctx, dict)
        ctx["ExistingAbstractions"] = [
            {"name": "BaseService", "type": "abstract class", "purpose": "base", "evidence": "src/"}
        ]
        ctx["PatternFingerprint"] = {
            "ExemplarImplementation": "src/main.py",
            "TestPattern": "pytest",
            "NamingPattern": "snake_case",
            "FileOrganization": "flat",
        }
        ctx["TechnicalDebtMarkers"] = ["TODO at src/legacy.py:10"]
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("CodebaseContext" in e for e in errors)


# ===========================================================================
# Edge-case tests
# ===========================================================================

@pytest.mark.governance
class TestBusinessRuleCandidatesEdge:
    """Unusual but technically valid/invalid edge inputs."""

    def test_candidate_rule_text_with_unicode(self, schema: dict) -> None:
        """Unicode in rule text must be accepted — business rules may be in any language."""
        c = _valid_candidate(
            candidate_rule_text="BR-C001: Überweisungsbetrag darf das Tageslimit nicht überschreiten"
        )
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("candidate_rule_text" in e for e in errors)

    def test_source_path_with_deep_nesting(self, schema: dict) -> None:
        """Deeply nested source paths must be accepted."""
        c = _valid_candidate(
            source_path="src/main/java/com/example/very/deeply/nested/pkg/Service.java"
        )
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("source_path" in e for e in errors)

    def test_fifty_candidates_accepted(self, schema: dict) -> None:
        """Large number of candidates must be accepted without error."""
        candidates = [
            _valid_candidate(
                id=f"BR-C{i:03d}",
                candidate_rule_text=f"BR-C{i:03d}: Rule number {i} must be enforced",
            )
            for i in range(1, 51)
        ]
        doc = _minimal_session_with_codebase_context(candidates)
        errors = validate_against_schema(schema=schema, value=doc)
        assert not any("BusinessRuleCandidates" in e for e in errors)

    def test_candidate_item_is_not_object(self, schema: dict) -> None:
        """Array items must be objects — a string item must fail."""
        doc = _minimal_session_with_codebase_context(["not an object"])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("BusinessRuleCandidates" in e for e in errors)

    def test_id_with_letters_after_prefix(self, schema: dict) -> None:
        """BR-CABC is not valid — digits required after BR-C."""
        c = _valid_candidate(id="BR-CABC")
        doc = _minimal_session_with_codebase_context([c])
        errors = validate_against_schema(schema=schema, value=doc)
        assert any("id:pattern" in e for e in errors)


# ===========================================================================
# Schema sync test — ensures JSON file and embedded Python stay aligned
# ===========================================================================

@pytest.mark.governance
class TestBusinessRuleCandidatesSchemaSync:
    """Verify JSON file schema and embedded schema agree on BusinessRuleCandidates."""

    def test_both_schemas_have_business_rule_candidates(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        json_path = (
            repo_root / "governance" / "assets" / "schemas" / "session_state.core.v1.schema.json"
        )
        with open(json_path, encoding="utf-8") as f:
            json_schema = json.load(f)

        # Navigate to CodebaseContext in JSON file
        json_ctx = (
            json_schema.get("properties", {})
            .get("SESSION_STATE", {})
            .get("properties", {})
            .get("CodebaseContext", {})
            .get("properties", {})
        )

        # Navigate to CodebaseContext in embedded schema
        embedded_ctx = (
            _HARDCODED_FALLBACK_SCHEMA.get("properties", {})
            .get("SESSION_STATE", {})
            .get("properties", {})
            .get("CodebaseContext", {})
            .get("properties", {})
        )

        assert "BusinessRuleCandidates" in json_ctx, "JSON schema missing BusinessRuleCandidates"
        assert "BusinessRuleCandidates" in embedded_ctx, "Embedded schema missing BusinessRuleCandidates"

    def test_required_fields_match_between_schemas(self) -> None:
        """Both schemas must require the same fields on candidate items."""
        repo_root = Path(__file__).resolve().parents[1]
        json_path = (
            repo_root / "governance" / "assets" / "schemas" / "session_state.core.v1.schema.json"
        )
        with open(json_path, encoding="utf-8") as f:
            json_schema = json.load(f)

        json_items = (
            json_schema.get("properties", {})
            .get("SESSION_STATE", {})
            .get("properties", {})
            .get("CodebaseContext", {})
            .get("properties", {})
            .get("BusinessRuleCandidates", {})
            .get("items", {})
        )
        embedded_items = (
            _HARDCODED_FALLBACK_SCHEMA.get("properties", {})
            .get("SESSION_STATE", {})
            .get("properties", {})
            .get("CodebaseContext", {})
            .get("properties", {})
            .get("BusinessRuleCandidates", {})
            .get("items", {})
        )

        assert set(json_items.get("required", [])) == set(embedded_items.get("required", []))

    def test_pattern_type_enums_match_between_schemas(self) -> None:
        """Both schemas must list the same pattern_type enum values."""
        repo_root = Path(__file__).resolve().parents[1]
        json_path = (
            repo_root / "governance" / "assets" / "schemas" / "session_state.core.v1.schema.json"
        )
        with open(json_path, encoding="utf-8") as f:
            json_schema = json.load(f)

        json_enum = (
            json_schema.get("properties", {})
            .get("SESSION_STATE", {})
            .get("properties", {})
            .get("CodebaseContext", {})
            .get("properties", {})
            .get("BusinessRuleCandidates", {})
            .get("items", {})
            .get("properties", {})
            .get("pattern_type", {})
            .get("enum", [])
        )
        embedded_enum = (
            _HARDCODED_FALLBACK_SCHEMA.get("properties", {})
            .get("SESSION_STATE", {})
            .get("properties", {})
            .get("CodebaseContext", {})
            .get("properties", {})
            .get("BusinessRuleCandidates", {})
            .get("items", {})
            .get("properties", {})
            .get("pattern_type", {})
            .get("enum", [])
        )

        assert json_enum == embedded_enum
        assert len(json_enum) == 7, f"Expected 7 pattern types, got {len(json_enum)}"
