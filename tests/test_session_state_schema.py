"""Tests for SESSION_STATE JSON Schema validation and invariant checking."""

from __future__ import annotations

import pytest

from governance.engine.schema_validator import validate_against_schema
from governance.engine._embedded_session_state_schema import SESSION_STATE_CORE_SCHEMA
from governance.engine.session_state_invariants import (
    validate_blocked_next_invariant,
    validate_confidence_mode_invariant,
    validate_profile_source_blocked_invariant,
    validate_reason_payloads_required,
    validate_session_state_invariants,
)


def _minimal_valid_session_state() -> dict[str, object]:
    return {
        "SESSION_STATE": {
            "session_state_version": 1,
            "ruleset_hash": "abc123",
            "Phase": "1",
            "Mode": "NORMAL",
            "OutputMode": "ARCHITECT",
            "ConfidenceLevel": 85,
            "Next": "Continue",
            "Bootstrap": {
                "Present": True,
                "Satisfied": True,
                "Evidence": "test",
            },
            "Scope": {},
            "RepoFacts": {},
            "LoadedRulebooks": {},
            "AddonsEvidence": {},
            "RulebookLoadEvidence": {},
            "ActiveProfile": "",
            "ProfileSource": "deferred",
            "ProfileEvidence": "",
            "Gates": {},
        }
    }


@pytest.mark.governance
class TestSchemaValidator:
    def test_validate_minimal_valid_document(self):
        doc = _minimal_valid_session_state()
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert errors == []

    def test_missing_required_key_session_state(self):
        doc = {}
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("SESSION_STATE:required" in e for e in errors)

    def test_missing_required_key_mode(self):
        doc = _minimal_valid_session_state()
        del doc["SESSION_STATE"]["Mode"]
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Mode:required" in e for e in errors)

    def test_invalid_mode_enum(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["Mode"] = "INVALID"
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Mode:enum" in e for e in errors)

    def test_confidence_out_of_range_high(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["ConfidenceLevel"] = 150
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("ConfidenceLevel:maximum" in e for e in errors)

    def test_confidence_out_of_range_low(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["ConfidenceLevel"] = -1
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("ConfidenceLevel:minimum" in e for e in errors)

    def test_invalid_phase_enum(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["Phase"] = "99"
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Phase:enum" in e for e in errors)

    def test_bootstrap_missing_required(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["Bootstrap"] = {}
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Bootstrap.Present:required" in e for e in errors)

    def test_feature_complexity_valid(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["FeatureComplexity"] = {
            "Class": "MODIFICATION",
            "Reason": "test",
            "PlanningDepth": "full",
        }
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert not any("FeatureComplexity" in e for e in errors)

    def test_feature_complexity_invalid_class(self):
        doc = _minimal_valid_session_state()
        doc["SESSION_STATE"]["FeatureComplexity"] = {
            "Class": "INVALID",
            "Reason": "test",
            "PlanningDepth": "full",
        }
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("FeatureComplexity.Class:enum" in e for e in errors)


@pytest.mark.governance
class TestInvariantValidators:
    def test_blocked_next_valid(self):
        state = {"Mode": "BLOCKED", "Next": "BLOCKED-TEST"}
        assert validate_blocked_next_invariant(state) == ()

    def test_blocked_next_missing_prefix(self):
        state = {"Mode": "BLOCKED", "Next": "Continue"}
        errors = validate_blocked_next_invariant(state)
        assert "blocked_next_missing_prefix" in errors

    def test_blocked_next_not_string(self):
        state = {"Mode": "BLOCKED", "Next": 123}
        errors = validate_blocked_next_invariant(state)
        assert "blocked_next_not_string" in errors

    def test_non_blocked_mode_skips_check(self):
        state = {"Mode": "NORMAL", "Next": "Continue"}
        assert validate_blocked_next_invariant(state) == ()

    def test_confidence_low_with_draft_ok(self):
        state = {"ConfidenceLevel": 50, "Mode": "DRAFT"}
        assert validate_confidence_mode_invariant(state) == ()

    def test_confidence_low_with_blocked_ok(self):
        state = {"ConfidenceLevel": 50, "Mode": "BLOCKED"}
        assert validate_confidence_mode_invariant(state) == ()

    def test_confidence_low_with_normal_fails(self):
        state = {"ConfidenceLevel": 50, "Mode": "NORMAL"}
        errors = validate_confidence_mode_invariant(state)
        assert "low_confidence_not_draft_or_blocked" in errors

    def test_confidence_high_with_normal_ok(self):
        state = {"ConfidenceLevel": 85, "Mode": "NORMAL"}
        assert validate_confidence_mode_invariant(state) == ()

    def test_ambiguous_profile_with_blocked_ok(self):
        state = {"ProfileSource": "ambiguous", "Mode": "BLOCKED"}
        assert validate_profile_source_blocked_invariant(state) == ()

    def test_ambiguous_profile_with_normal_fails(self):
        state = {"ProfileSource": "ambiguous", "Mode": "NORMAL"}
        errors = validate_profile_source_blocked_invariant(state)
        assert "ambiguous_profile_not_blocked" in errors

    def test_non_ambiguous_profile_skips_check(self):
        state = {"ProfileSource": "user-explicit", "Mode": "NORMAL"}
        assert validate_profile_source_blocked_invariant(state) == ()

    def test_reason_payloads_present_ok(self):
        state = {
            "Mode": "BLOCKED",
            "Next": "BLOCKED-TEST",
            "Diagnostics": {"ReasonPayloads": [{"reason_code": "BLOCKED-TEST", "surface": "test"}]},
        }
        assert validate_reason_payloads_required(state) == ()

    def test_reason_payloads_missing_fails(self):
        state = {"Mode": "BLOCKED", "Next": "BLOCKED-TEST"}
        errors = validate_reason_payloads_required(state)
        assert "missing_diagnostics_for_reason_code" in errors

    def test_reason_payloads_empty_fails(self):
        state = {"Mode": "BLOCKED", "Next": "BLOCKED-TEST", "Diagnostics": {"ReasonPayloads": []}}
        errors = validate_reason_payloads_required(state)
        assert "missing_reason_payloads" in errors


@pytest.mark.governance
class TestFullInvariantValidation:
    def test_all_invariants_pass(self):
        doc = {
            "SESSION_STATE": {
                "Mode": "NORMAL",
                "ConfidenceLevel": 85,
                "ProfileSource": "user-explicit",
                "Next": "Continue",
            }
        }
        assert validate_session_state_invariants(doc) == ()

    def test_multiple_violations(self):
        doc = {
            "SESSION_STATE": {
                "Mode": "BLOCKED",
                "ConfidenceLevel": 50,
                "ProfileSource": "ambiguous",
                "Next": "Continue",  # should be BLOCKED-
            }
        }
        errors = validate_session_state_invariants(doc)
        assert "blocked_next_missing_prefix" in errors

    def test_missing_session_state_key(self):
        doc = {}
        errors = validate_session_state_invariants(doc)
        assert "missing_session_state_key" in errors
