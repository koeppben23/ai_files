"""Tests for Phase-5 Normalizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.application.services.phase5_normalizer import (
    canonicalize_legacy_p5x_surface,
    sync_conditional_p5_gate_states,
    normalize_phase6_p5_state,
)


class TestCanonicalizeLegacyP5xSurface:
    """Tests for canonicalize_legacy_p5x_surface."""

    def test_no_action_for_non_architecture_review_phase(self):
        """No changes when phase is not 5-ArchitectureReview."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "4-TicketIntake",
                "Next": "4",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        assert state_doc["SESSION_STATE"]["Phase"] == "4-TicketIntake"

    def test_canonicalizes_to_54_business_rules(self):
        """Canonicalizes 5-ArchitectureReview with 5.4 next to 5.4-BusinessRules."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "Next": "5.4",
                "active_gate": "Architecture Review Gate",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["Phase"] == "5.4-BusinessRules"
        assert state["Next"] == "5.4"
        assert state["active_gate"] == "Business Rules Validation"

    def test_canonicalizes_to_55_technical_debt(self):
        """Canonicalizes 5-ArchitectureReview with blocked P5.5 gate."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "Next": "5",
                "active_gate": "Technical Debt Gate",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["Phase"] == "5.5-TechnicalDebt"
        assert state["Next"] == "5.5"

    def test_canonicalizes_to_56_rollback_safety(self):
        """Canonicalizes 5-ArchitectureReview with blocked P5.6 gate."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "Next": "5",
                "next_gate_condition": "BLOCKED-P5-6-ROLLBACK-SAFETY-GATE",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["Phase"] == "5.6-RollbackSafety"
        assert state["Next"] == "5.6"

    def test_no_canonicalization_when_no_match(self):
        """No changes when no target gate matches."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "Next": "5",
                "active_gate": "Unknown Gate",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["Phase"] == "5-ArchitectureReview"

    def test_updates_normalization_marker(self):
        """Updates _p6_state_normalization marker when present."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "Next": "5.4",
                "_p6_state_normalization": {},
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        marker = state_doc["SESSION_STATE"]["_p6_state_normalization"]
        assert marker["corrected_phase"] == "5.4-BusinessRules"
        assert marker["corrected_next"] == "5.4"
        assert marker["corrected_active_gate"] == "Business Rules Validation"


class TestNormalizePhase6P5State:
    """Tests for normalize_phase6_p5_state."""

    def test_no_action_for_non_phase6(self):
        """No changes when phase does not start with 6."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "5.4-BusinessRules",
                "Next": "5.4",
                "Gates": {
                    "P5.4-BusinessRules": "pending",
                },
            }
        }
        normalize_phase6_p5_state(state_doc=state_doc)
        assert state_doc["SESSION_STATE"]["Phase"] == "5.4-BusinessRules"

    def test_no_action_when_no_gates_dict(self):
        """No changes when Gates is not a dict."""
        state_doc = {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "Next": "6",
            }
        }
        normalize_phase6_p5_state(state_doc=state_doc)
        # Should not crash and no changes
        assert "Gates" not in state_doc["SESSION_STATE"] or isinstance(
            state_doc["SESSION_STATE"].get("Gates"), dict
        )

    def test_resets_when_p5_gates_open(self):
        """Resets to P5 when P5 gates are non-terminal in phase 6."""
        # This test requires gate_evaluator to be available
        pytest.importorskip("governance_runtime.engine.gate_evaluator")
        pytest.importorskip("governance_runtime.kernel.phase_kernel")

        state_doc = {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "Next": "6",
                "active_gate": "Post Flight",
                "Gates": {
                    "P5-Architecture": "approved",
                    "P5.3-TestQuality": "pass",
                    "P5.4-BusinessRules": "pending",  # Open gate
                    "P5.5-TechnicalDebt": "approved",
                    "P5.6-RollbackSafety": "approved",
                },
            }
        }
        normalize_phase6_p5_state(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]

        # Should have reset to P5.4
        assert state["Phase"] == "5.4-BusinessRules"
        assert state["phase6_state"] == "phase5_in_progress"
        assert state["implementation_review_complete"] is False
        assert "_p6_state_normalization" in state
        assert "P5.4-BusinessRules" in state["_p6_state_normalization"]["open_gates"]

    def test_no_action_when_all_gates_terminal(self):
        """No reset when all P5 gates are in terminal states."""
        pytest.importorskip("governance_runtime.engine.gate_evaluator")
        pytest.importorskip("governance_runtime.kernel.phase_kernel")

        state_doc = {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "Next": "6",
                "active_gate": "Post Flight",
                "Gates": {
                    "P5-Architecture": "approved",
                    "P5.3-TestQuality": "pass",
                    "P5.4-BusinessRules": "compliant",
                    "P5.5-TechnicalDebt": "approved",
                    "P5.6-RollbackSafety": "approved",
                },
            }
        }
        normalize_phase6_p5_state(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]

        # Should remain in phase 6
        assert state["Phase"] == "6-PostFlight"
        assert "_p6_state_normalization" not in state


class TestSyncConditionalP5GateStates:
    """Tests for sync_conditional_p5_gate_states."""

    def test_no_action_without_gates(self):
        """No changes when state has no Gates dict."""
        state_doc = {"SESSION_STATE": {}}
        sync_conditional_p5_gate_states(state_doc=state_doc)
        # Should not crash
        assert "Gates" not in state_doc["SESSION_STATE"]

    def test_no_action_when_gates_not_dict(self):
        """No changes when Gates is not a dict."""
        state_doc = {"SESSION_STATE": {"Gates": "not a dict"}}
        sync_conditional_p5_gate_states(state_doc=state_doc)
        assert state_doc["SESSION_STATE"]["Gates"] == "not a dict"
