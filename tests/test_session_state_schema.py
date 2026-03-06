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
    validate_canonical_path_invariants,
    validate_p5_approved_architecture_decisions,
    validate_phase_gate_prerequisites,
    validate_gate_artifacts_integrity,
    validate_ticket_intake_ready_invariant,
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
            "ActiveProfile": None,
            "ProfileSource": None,
            "ProfileEvidence": None,
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
        json_path = repo_root / "governance" / "assets" / "schemas" / "session_state.core.v1.schema.json"
        with open(json_path, encoding="utf-8") as f:
            json_schema = json.load(f)

        # Compare key structural elements
        assert isinstance(json_schema, dict)
        assert isinstance(_HARDCODED_FALLBACK_SCHEMA, dict)
        assert json_schema["required"] == _HARDCODED_FALLBACK_SCHEMA["required"]
        json_properties = json_schema.get("properties")
        assert isinstance(json_properties, dict)
        json_root = json_properties["SESSION_STATE"]
        assert isinstance(json_root, dict)
        json_props = json_root.get("properties")
        assert isinstance(json_props, dict)
        fallback_schema = _HARDCODED_FALLBACK_SCHEMA
        fallback_properties = fallback_schema.get("properties")
        assert isinstance(fallback_properties, dict)
        fallback_root = fallback_properties["SESSION_STATE"]
        assert isinstance(fallback_root, dict)
        fallback_props = fallback_root.get("properties")
        assert isinstance(fallback_props, dict)
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

    def test_ticket_intake_ready_ok(self):
        state: dict[str, object] = {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "Bootstrap": {"Satisfied": True},
            "ticket_intake_ready": True,
            "phase_ready": 4,
        }
        assert validate_ticket_intake_ready_invariant(state) == ()

    def test_ticket_intake_ready_blocks_without_bootstrap_satisfied(self):
        state: dict[str, object] = {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "Bootstrap": {"Satisfied": False},
            "ticket_intake_ready": True,
        }
        errors = validate_ticket_intake_ready_invariant(state)
        assert "ticket_intake_ready_without_bootstrap_satisfied" in errors

    def test_ticket_intake_ready_blocks_without_persistence_committed(self):
        state: dict[str, object] = {
            "Phase": "4",
            "PersistenceCommitted": False,
            "WorkspaceReadyGateCommitted": True,
            "Bootstrap": {"Satisfied": True},
            "ticket_intake_ready": True,
        }
        errors = validate_ticket_intake_ready_invariant(state)
        assert "ticket_intake_ready_without_persistence_committed" in errors

    def test_ticket_intake_ready_blocks_without_workspace_ready_gate(self):
        state: dict[str, object] = {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": False,
            "Bootstrap": {"Satisfied": True},
            "ticket_intake_ready": True,
        }
        errors = validate_ticket_intake_ready_invariant(state)
        assert "ticket_intake_ready_without_workspace_ready_gate" in errors

    def test_ticket_intake_ready_blocks_below_phase_4(self):
        state: dict[str, object] = {
            "Phase": "3A",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "Bootstrap": {"Satisfied": True},
            "ticket_intake_ready": True,
        }
        errors = validate_ticket_intake_ready_invariant(state)
        assert "ticket_intake_ready_below_phase_4" in errors

    def test_ticket_intake_ready_blocks_phase_ready_below_4(self):
        state: dict[str, object] = {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "Bootstrap": {"Satisfied": True},
            "ticket_intake_ready": True,
            "phase_ready": 3,
        }
        errors = validate_ticket_intake_ready_invariant(state)
        assert "ticket_intake_ready_phase_ready_below_4" in errors

    def test_ticket_intake_ready_missing_when_preconditions_met(self):
        state: dict[str, object] = {
            "Phase": "4",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "Bootstrap": {"Satisfied": True},
            "ticket_intake_ready": False,
        }
        errors = validate_ticket_intake_ready_invariant(state)
        assert "ticket_intake_ready_missing_when_preconditions_met" in errors

    def test_ticket_intake_ready_false_skips_checks(self):
        state: dict[str, object] = {"ticket_intake_ready": False}
        assert validate_ticket_intake_ready_invariant(state) == ()

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
        assert "missing_governance_for_reason_code" in errors

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

    def test_fresh_phase4_start_requires_fail_closed_business_rules(self):
        doc: dict[str, object] = {
            "SESSION_STATE": {
                "Phase": "4",
                "phase": "4",
                "Mode": "IN_PROGRESS",
                "active_gate": "Ticket Input Gate",
                "phase4_intake_source": "new-work-session",
                "Ticket": None,
                "Task": None,
                "TicketRecordDigest": None,
                "TaskRecordDigest": None,
                "phase_transition_evidence": True,
                "Scope": {"BusinessRules": "extracted"},
                "BusinessRules": {
                    "Decision": "execute",
                    "Outcome": "extracted",
                    "ExecutionEvidence": True,
                    "InventoryFileStatus": "written",
                    "Rules": ["BR-1: stale"],
                    "Evidence": ["docs/rules.md:1"],
                },
            }
        }

        errors = validate_session_state_invariants(doc)
        assert "fresh_phase4_phase_transition_evidence_not_false" in errors
        assert "fresh_phase4_scope_business_rules_not_unresolved" in errors
        assert "fresh_phase4_execution_evidence_not_false" in errors
        assert "fresh_phase4_inventory_file_status_written" in errors
        assert "fresh_phase4_outcome_extracted" in errors
        assert "fresh_phase4_rules_references_present" in errors
        assert "fresh_phase4_evidence_references_present" in errors

    def test_non_fresh_phase4_context_skips_fresh_start_invariant(self):
        doc: dict[str, object] = {
            "SESSION_STATE": {
                "Phase": "4",
                "active_gate": "Plan Record Preparation Gate",
                "phase4_intake_source": "phase4-intake-bridge",
                "Ticket": "T-123",
                "phase_transition_evidence": True,
                "Scope": {"BusinessRules": "extracted"},
                "BusinessRules": {
                    "ExecutionEvidence": True,
                    "InventoryFileStatus": "written",
                    "Outcome": "extracted",
                },
            }
        }

        errors = validate_session_state_invariants(doc)
        assert "fresh_phase4_phase_transition_evidence_not_false" not in errors


@pytest.mark.governance
class TestPathInvariantValidation:
    def test_valid_variable_path(self):
        state: dict[str, object] = {"RepoCacheFile": {"TargetPath": "${WORKSPACES_HOME}/cache.yaml"}}
        errors = validate_canonical_path_invariants(state)
        assert errors == ()

    def test_backslash_in_path_blocked(self):
        state: dict[str, object] = {"TargetPath": "C:\\Users\\test"}
        errors = validate_canonical_path_invariants(state)
        assert any("backslash" in e for e in errors)
        assert any("BLOCKED-PERSISTENCE-PATH-VIOLATION" in e for e in errors)

    def test_drive_prefix_blocked(self):
        state: dict[str, object] = {"SourcePath": "C:/Users/test"}
        errors = validate_canonical_path_invariants(state)
        assert any("drive_prefix" in e for e in errors)

    def test_parent_traversal_blocked(self):
        state: dict[str, object] = {"FilePath": "../secret/file.txt"}
        errors = validate_canonical_path_invariants(state)
        assert any("parent_traversal" in e for e in errors)

    def test_single_drive_letter_degenerate(self):
        state: dict[str, object] = {"TargetPath": "C"}
        errors = validate_canonical_path_invariants(state)
        assert any("single_drive_letter" in e for e in errors)
        assert any("BLOCKED-PERSISTENCE-TARGET-DEGENERATE" in e for e in errors)

    def test_drive_root_token_degenerate(self):
        state: dict[str, object] = {"TargetPath": "C:"}
        errors = validate_canonical_path_invariants(state)
        assert any("drive_root_token" in e for e in errors)

    def test_single_segment_without_variable_degenerate(self):
        state: dict[str, object] = {"TargetPath": "rules.md"}
        errors = validate_canonical_path_invariants(state)
        assert any("single_segment_without_variable" in e for e in errors)

    def test_single_segment_with_variable_ok(self):
        state: dict[str, object] = {"TargetPath": "${WORKSPACES_HOME}/file.txt"}
        errors = validate_canonical_path_invariants(state)
        assert errors == ()

    def test_nested_path_field_validated(self):
        state: dict[str, object] = {
            "RepoMapDigestFile": {
                "SourcePath": "C:\\bad\\path",
                "TargetPath": "${WORKSPACES_HOME}/good/path",
            }
        }
        errors = validate_canonical_path_invariants(state)
        assert any("backslash" in e for e in errors)

    def test_non_path_field_ignored(self):
        state: dict[str, object] = {
            "SomeOtherField": "C:\\ignored",
            "Evidence": "backslashes OK in evidence",
        }
        errors = validate_canonical_path_invariants(state)
        assert errors == ()

    def test_empty_path_ignored(self):
        state: dict[str, object] = {"TargetPath": ""}
        errors = validate_canonical_path_invariants(state)
        assert errors == ()

    def test_path_invariant_integrated_in_full_validation(self):
        doc: dict[str, object] = {
            "SESSION_STATE": {
                "Mode": "NORMAL",
                "ConfidenceLevel": 85,
                "ProfileSource": "user-explicit",
                "Next": "Continue",
                "OutputMode": "IMPLEMENT",
                "LoadedRulebooks": {},
                "TargetPath": "C:\\bad",
            }
        }
        errors = validate_session_state_invariants(doc)
        assert any("backslash" in e for e in errors)


@pytest.mark.governance
class TestP5ArchitectureDecisionsInvariant:
    def test_p5_approved_with_valid_architecture_decisions(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "approved"},
            "ArchitectureDecisions": [
                {"ID": "AD-001", "Status": "approved", "Decision": "Use PostgreSQL"}
            ],
        }
        errors = validate_p5_approved_architecture_decisions(state)
        assert errors == ()

    def test_p5_approved_without_architecture_decisions(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "approved"},
            "ArchitectureDecisions": [],
        }
        errors = validate_p5_approved_architecture_decisions(state)
        assert "p5_approved_without_architecture_decisions" in errors

    def test_p5_approved_with_only_proposed_decisions(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "approved"},
            "ArchitectureDecisions": [
                {"ID": "AD-001", "Status": "proposed", "Decision": "Use PostgreSQL"}
            ],
        }
        errors = validate_p5_approved_architecture_decisions(state)
        assert "p5_approved_without_approved_decision_entry" in errors

    def test_p5_pending_skips_check(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "pending"},
        }
        errors = validate_p5_approved_architecture_decisions(state)
        assert errors == ()


@pytest.mark.governance
class TestPhaseGatePrerequisitesInvariant:
    def test_phase5_implementation_requires_p5_approved(self):
        state: dict[str, object] = {
            "Phase": "5.1-Implement",
            "Gates": {"P5-Architecture": "pending"},
        }
        errors = validate_phase_gate_prerequisites(state)
        assert "phase5_without_p5_approved" in errors

    def test_phase6_requires_p5_approved_and_p53_pass(self):
        state: dict[str, object] = {
            "Phase": "6-ImplementationQA",
            "Gates": {"P5-Architecture": "approved", "P5.3-TestQuality": "pending"},
        }
        errors = validate_phase_gate_prerequisites(state)
        assert "phase6_without_p53_pass" in errors

    def test_phase6_with_all_prerequisites_ok(self):
        state: dict[str, object] = {
            "Phase": "6-ImplementationQA",
            "Gates": {"P5-Architecture": "approved", "P5.3-TestQuality": "pass"},
        }
        errors = validate_phase_gate_prerequisites(state)
        assert errors == ()

    def test_phase4_skips_check(self):
        state: dict[str, object] = {
            "Phase": "4-Plan",
            "Gates": {},
        }
        errors = validate_phase_gate_prerequisites(state)
        assert errors == ()

    def test_phase5_architecture_review_skips_code_prereq_check(self):
        state: dict[str, object] = {
            "Phase": "5-ArchitectureReview",
            "Gates": {"P5-Architecture": "pending"},
        }
        errors = validate_phase_gate_prerequisites(state)
        assert errors == ()

    def test_code_step_without_p5_approved(self):
        state: dict[str, object] = {
            "Phase": "5",
            "PhaseRouterFacts": {"next_action_class": "code_producing"},
            "Gates": {"P5-Architecture": "pending"},
        }
        errors = validate_phase_gate_prerequisites(state)
        assert "code_step_without_p5_approved" in errors


@pytest.mark.governance
class TestGateArtifactsIntegrityInvariant:
    def test_gate_approved_with_all_artifacts_present(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "approved"},
            "GateArtifacts": {
                "P5-Architecture": {
                    "Required": ["DecisionPack"],
                    "Provided": {"DecisionPack": "present"},
                }
            },
        }
        errors = validate_gate_artifacts_integrity(state)
        assert errors == ()

    def test_gate_approved_with_missing_artifact_fails(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "approved"},
            "GateArtifacts": {
                "P5-Architecture": {
                    "Required": ["DecisionPack", "TouchedSurface"],
                    "Provided": {"DecisionPack": "present", "TouchedSurface": "missing"},
                }
            },
        }
        errors = validate_gate_artifacts_integrity(state)
        assert any("missing_artifacts" in e for e in errors)

    def test_gate_pending_with_missing_artifact_ok(self):
        state: dict[str, object] = {
            "Gates": {"P5-Architecture": "pending"},
            "GateArtifacts": {
                "P5-Architecture": {
                    "Required": ["DecisionPack"],
                    "Provided": {"DecisionPack": "missing"},
                }
            },
        }
        errors = validate_gate_artifacts_integrity(state)
        assert errors == ()

    def test_no_gate_artifacts_skips_check(self):
        state: dict[str, object] = {"Gates": {"P5-Architecture": "approved"}}
        errors = validate_gate_artifacts_integrity(state)
        assert errors == ()
