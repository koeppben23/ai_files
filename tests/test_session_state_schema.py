"""Tests for SESSION_STATE JSON Schema validation and invariant checking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.engine.schema_validator import validate_against_schema
from governance.engine._embedded_session_state_schema import (
    SESSION_STATE_CORE_SCHEMA,
    _HARDCODED_FALLBACK_SCHEMA,
)
from governance.engine.session_state_invariants import (
    validate_blocked_next_invariant,
    validate_confidence_mode_invariant,
    validate_profile_source_blocked_invariant,
    validate_reason_payloads_required,
    validate_output_mode_architect_invariant,
    validate_rulebook_evidence_mirror,
    validate_addon_evidence_mirror,
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
            "DecisionSurface": {},  # Required for ARCHITECT mode
        }
    }


@pytest.mark.governance
class TestSchemaValidator:
    def test_validate_minimal_valid_document(self):
        doc = _minimal_valid_session_state()
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert errors == []

    def test_missing_required_key_session_state(self):
        doc: dict[str, object] = {}
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("SESSION_STATE:required" in e for e in errors)

    def test_missing_required_key_mode(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state.pop("Mode", None)
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Mode:required" in e for e in errors)

    def test_invalid_mode_enum(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["Mode"] = "INVALID"
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Mode:enum" in e for e in errors)

    def test_confidence_out_of_range_high(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["ConfidenceLevel"] = 150
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("ConfidenceLevel:maximum" in e for e in errors)

    def test_confidence_out_of_range_low(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["ConfidenceLevel"] = -1
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("ConfidenceLevel:minimum" in e for e in errors)

    def test_invalid_phase_enum(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["Phase"] = "99"
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Phase:enum" in e for e in errors)

    def test_bootstrap_missing_required(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["Bootstrap"] = {}
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("Bootstrap.Present:required" in e for e in errors)

    def test_feature_complexity_valid(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["FeatureComplexity"] = {
            "Class": "MODIFICATION",
            "Reason": "test",
            "PlanningDepth": "full",
        }
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert not any("FeatureComplexity" in e for e in errors)

    def test_feature_complexity_invalid_class(self):
        doc = _minimal_valid_session_state()
        session_state = doc["SESSION_STATE"]
        assert isinstance(session_state, dict)
        session_state["FeatureComplexity"] = {
            "Class": "INVALID",
            "Reason": "test",
            "PlanningDepth": "full",
        }
        errors = validate_against_schema(schema=SESSION_STATE_CORE_SCHEMA, value=doc)
        assert any("FeatureComplexity.Class:enum" in e for e in errors)

    def test_schema_sync_between_json_and_fallback(self):
        """Verify the hardcoded fallback matches the JSON file."""
        repo_root = Path(__file__).resolve().parents[1]
        json_path = repo_root / "diagnostics" / "schemas" / "session_state.core.v1.schema.json"
        with open(json_path, encoding="utf-8") as f:
            json_schema = json.load(f)

        # Compare key structural elements
        assert json_schema["required"] == _HARDCODED_FALLBACK_SCHEMA["required"]
        json_props = json_schema["properties"]["SESSION_STATE"]["properties"]
        fallback_props = _HARDCODED_FALLBACK_SCHEMA["properties"]["SESSION_STATE"]["properties"]
        assert set(json_props.keys()) == set(fallback_props.keys())


@pytest.mark.governance
class TestInvariantValidators:
    def test_blocked_next_valid(self):
        state: dict[str, object] = {"Mode": "BLOCKED", "Next": "BLOCKED-TEST"}
        assert validate_blocked_next_invariant(state) == ()

    def test_blocked_next_missing_prefix(self):
        state: dict[str, object] = {"Mode": "BLOCKED", "Next": "Continue"}
        errors = validate_blocked_next_invariant(state)
        assert "blocked_next_missing_prefix" in errors

    def test_blocked_next_not_string(self):
        state: dict[str, object] = {"Mode": "BLOCKED", "Next": 123}
        errors = validate_blocked_next_invariant(state)
        assert "blocked_next_not_string" in errors

    def test_non_blocked_mode_skips_check(self):
        state: dict[str, object] = {"Mode": "NORMAL", "Next": "Continue"}
        assert validate_blocked_next_invariant(state) == ()

    def test_confidence_low_with_draft_ok(self):
        state: dict[str, object] = {"ConfidenceLevel": 50, "Mode": "DRAFT"}
        assert validate_confidence_mode_invariant(state) == ()

    def test_confidence_low_with_blocked_ok(self):
        state: dict[str, object] = {"ConfidenceLevel": 50, "Mode": "BLOCKED"}
        assert validate_confidence_mode_invariant(state) == ()

    def test_confidence_low_with_normal_fails(self):
        state: dict[str, object] = {"ConfidenceLevel": 50, "Mode": "NORMAL"}
        errors = validate_confidence_mode_invariant(state)
        assert "low_confidence_not_draft_or_blocked" in errors

    def test_confidence_high_with_normal_ok(self):
        state: dict[str, object] = {"ConfidenceLevel": 85, "Mode": "NORMAL"}
        assert validate_confidence_mode_invariant(state) == ()

    def test_ambiguous_profile_with_blocked_ok(self):
        state: dict[str, object] = {"ProfileSource": "ambiguous", "Mode": "BLOCKED"}
        assert validate_profile_source_blocked_invariant(state) == ()

    def test_ambiguous_profile_with_normal_fails(self):
        state: dict[str, object] = {"ProfileSource": "ambiguous", "Mode": "NORMAL"}
        errors = validate_profile_source_blocked_invariant(state)
        assert "ambiguous_profile_not_blocked" in errors

    def test_non_ambiguous_profile_skips_check(self):
        state: dict[str, object] = {"ProfileSource": "user-explicit", "Mode": "NORMAL"}
        assert validate_profile_source_blocked_invariant(state) == ()

    def test_reason_payloads_present_ok(self):
        state: dict[str, object] = {
            "Mode": "BLOCKED",
            "Next": "BLOCKED-TEST",
            "Diagnostics": {"ReasonPayloads": [{"reason_code": "BLOCKED-TEST", "surface": "test"}]},
        }
        assert validate_reason_payloads_required(state) == ()

    def test_reason_payloads_missing_fails(self):
        state: dict[str, object] = {"Mode": "BLOCKED", "Next": "BLOCKED-TEST"}
        errors = validate_reason_payloads_required(state)
        assert "missing_diagnostics_for_reason_code" in errors

    def test_reason_payloads_empty_fails(self):
        state: dict[str, object] = {"Mode": "BLOCKED", "Next": "BLOCKED-TEST", "Diagnostics": {"ReasonPayloads": []}}
        errors = validate_reason_payloads_required(state)
        assert "missing_reason_payloads" in errors

    def test_architect_mode_with_decision_surface_ok(self):
        state: dict[str, object] = {"OutputMode": "ARCHITECT", "DecisionSurface": {}}
        assert validate_output_mode_architect_invariant(state) == ()

    def test_architect_mode_missing_decision_surface(self):
        state: dict[str, object] = {"OutputMode": "ARCHITECT"}
        errors = validate_output_mode_architect_invariant(state)
        assert "architect_mode_missing_decision_surface" in errors

    def test_non_architect_mode_skips_decision_surface_check(self):
        state: dict[str, object] = {"OutputMode": "IMPLEMENT"}
        assert validate_output_mode_architect_invariant(state) == ()

    def test_rulebook_evidence_mirror_ok(self):
        state: dict[str, object] = {
            "LoadedRulebooks": {"core": "master.md"},
            "RulebookLoadEvidence": {"core": {"hash": "abc"}},
        }
        assert validate_rulebook_evidence_mirror(state) == ()

    def test_rulebook_evidence_missing_when_core_loaded(self):
        state: dict[str, object] = {"LoadedRulebooks": {"core": "master.md"}}
        errors = validate_rulebook_evidence_mirror(state)
        assert "missing_rulebook_load_evidence" in errors

    def test_rulebook_evidence_missing_core_key(self):
        state: dict[str, object] = {
            "LoadedRulebooks": {"core": "master.md"},
            "RulebookLoadEvidence": {},
        }
        errors = validate_rulebook_evidence_mirror(state)
        assert "rulebook_evidence_missing_core" in errors

    def test_no_core_loaded_skips_check(self):
        state: dict[str, object] = {"LoadedRulebooks": {}}
        assert validate_rulebook_evidence_mirror(state) == ()

    def test_addon_evidence_mirror_ok(self):
        state: dict[str, object] = {
            "LoadedRulebooks": {"addons": {"kafka": "kafka.md"}},
            "AddonsEvidence": {"kafka": {"activated": True}},
        }
        assert validate_addon_evidence_mirror(state) == ()

    def test_addon_evidence_missing(self):
        state: dict[str, object] = {
            "LoadedRulebooks": {"addons": {"kafka": "kafka.md"}},
            "AddonsEvidence": {},
        }
        errors = validate_addon_evidence_mirror(state)
        assert any("addons_evidence_missing" in e for e in errors)

    def test_no_addons_loaded_skips_check(self):
        state: dict[str, object] = {"LoadedRulebooks": {}}
        assert validate_addon_evidence_mirror(state) == ()


@pytest.mark.governance
class TestFullInvariantValidation:
    def test_all_invariants_pass(self):
        doc: dict[str, object] = {
            "SESSION_STATE": {
                "Mode": "NORMAL",
                "ConfidenceLevel": 85,
                "ProfileSource": "user-explicit",
                "Next": "Continue",
                "OutputMode": "IMPLEMENT",
                "LoadedRulebooks": {},
            }
        }
        assert validate_session_state_invariants(doc) == ()

    def test_multiple_violations(self):
        doc: dict[str, object] = {
            "SESSION_STATE": {
                "Mode": "BLOCKED",
                "ConfidenceLevel": 50,
                "ProfileSource": "ambiguous",
                "Next": "Continue",
            }
        }
        errors = validate_session_state_invariants(doc)
        assert "blocked_next_missing_prefix" in errors

    def test_missing_session_state_key(self):
        doc: dict[str, object] = {}
        errors = validate_session_state_invariants(doc)
        assert "missing_session_state_key" in errors
