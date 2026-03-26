"""Tests for phase-5 Normalizer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from governance_runtime.application.services.phase5_normalizer import (
    canonicalize_legacy_p5x_surface,
    sync_conditional_p5_gate_states,
    normalize_phase6_p5_state,
    GateConstants,
    GateEvaluators,
)


# Mock gate evaluators for testing
@dataclass(frozen=True)
class MockGateEvaluation:
    """Mock gate evaluation result."""
    gate_key: str
    status: str
    reason_code: str = ""
    details: str = ""


def _mock_phase_1_5_executed(state: dict) -> bool:
    """Mock phase_1_5_executed that returns False."""
    return False


def _mock_evaluate_p53(**kwargs) -> MockGateEvaluation:
    """Mock P5.3 evaluator."""
    return MockGateEvaluation(gate_key="P5.3-TestQuality", status="pass")


def _mock_evaluate_p54(**kwargs) -> MockGateEvaluation:
    """Mock P5.4 evaluator."""
    return MockGateEvaluation(gate_key="P5.4-BusinessRules", status="compliant")


def _mock_evaluate_p55(**kwargs) -> MockGateEvaluation:
    """Mock P5.5 evaluator."""
    return MockGateEvaluation(gate_key="P5.5-TechnicalDebt", status="approved")


def _mock_evaluate_p56(**kwargs) -> MockGateEvaluation:
    """Mock P5.6 evaluator."""
    return MockGateEvaluation(gate_key="P5.6-RollbackSafety", status="approved")


def _mock_reason_code_for_gate(gate_key: str) -> str:
    """Mock reason_code_for_gate."""
    return f"BLOCKED-{gate_key}"


# Test fixtures
MOCK_GATE_EVALUATORS = GateEvaluators(
    evaluate_p53=_mock_evaluate_p53,
    evaluate_p54=_mock_evaluate_p54,
    evaluate_p55=_mock_evaluate_p55,
    evaluate_p56=_mock_evaluate_p56,
    phase_1_5_executed=_mock_phase_1_5_executed,
)

MOCK_GATE_CONSTANTS = GateConstants(
    priority_order=(
        "P5-Architecture",
        "P5.3-TestQuality",
        "P5.4-BusinessRules",
        "P5.5-TechnicalDebt",
        "P5.6-RollbackSafety",
    ),
    terminal_values={
        "P5-Architecture": ("approved",),
        "P5.3-TestQuality": ("pass", "pass-with-exceptions", "not-applicable"),
        "P5.4-BusinessRules": ("compliant", "compliant-with-exceptions", "not-applicable"),
        "P5.5-TechnicalDebt": ("approved", "not-applicable"),
        "P5.6-RollbackSafety": ("approved", "not-applicable"),
    },
    reason_code_for_gate=_mock_reason_code_for_gate,
)


class TestCanonicalizeLegacyP5xSurface:
    """Tests for canonicalize_legacy_p5x_surface."""

    def test_no_action_for_non_architecture_review_phase(self):
        """No changes when phase is not 5-ArchitectureReview."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "4-TicketIntake",
                "next": "4",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        assert state_doc["SESSION_STATE"]["phase"] == "4-TicketIntake"

    def test_canonicalizes_to_54_business_rules(self):
        """Canonicalizes 5-ArchitectureReview with 5.4 next to 5.4-BusinessRules."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5.4",
                "active_gate": "Architecture Review Gate",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["phase"] == "5.4-BusinessRules"
        assert state["next"] == "5.4"
        assert state["active_gate"] == "Business Rules Validation"

    def test_canonicalizes_to_55_technical_debt(self):
        """Canonicalizes 5-ArchitectureReview with blocked P5.5 gate."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5",
                "active_gate": "Technical Debt Gate",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["phase"] == "5.5-TechnicalDebt"
        assert state["next"] == "5.5"

    def test_canonicalizes_to_56_rollback_safety(self):
        """Canonicalizes 5-ArchitectureReview with blocked P5.6 gate."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5",
                "next_gate_condition": "BLOCKED-P5-6-ROLLBACK-SAFETY-GATE",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["phase"] == "5.6-RollbackSafety"
        assert state["next"] == "5.6"

    def test_no_canonicalization_when_no_match(self):
        """No changes when no target gate matches."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5",
                "active_gate": "Unknown Gate",
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        state = state_doc["SESSION_STATE"]
        assert state["phase"] == "5-ArchitectureReview"

    def test_updates_normalization_marker(self):
        """Updates _p6_state_normalization marker when present."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5.4",
                "_p6_state_normalization": {},
            }
        }
        canonicalize_legacy_p5x_surface(state_doc=state_doc)
        marker = state_doc["SESSION_STATE"]["_p6_state_normalization"]
        assert marker["corrected_phase"] == "5.4-BusinessRules"
        assert marker["corrected_next"] == "5.4"
        assert marker["corrected_active_gate"] == "Business Rules Validation"


class TestNormalizephase6P5State:
    """Tests for normalize_phase6_p5_state."""

    def test_no_action_for_non_phase6(self):
        """No changes when phase does not start with 6."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5.4-BusinessRules",
                "next": "5.4",
                "Gates": {
                    "P5.4-BusinessRules": "pending",
                },
            }
        }
        normalize_phase6_p5_state(
            state_doc=state_doc,
            gate_constants=MOCK_GATE_CONSTANTS,
            gate_evaluators=MOCK_GATE_EVALUATORS,
        )
        assert state_doc["SESSION_STATE"]["phase"] == "5.4-BusinessRules"

    def test_no_action_when_no_gates_dict(self):
        """No changes when Gates is not a dict."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
            }
        }
        normalize_phase6_p5_state(
            state_doc=state_doc,
            gate_constants=MOCK_GATE_CONSTANTS,
            gate_evaluators=MOCK_GATE_EVALUATORS,
        )
        # Should not crash and no changes
        assert "Gates" not in state_doc["SESSION_STATE"] or isinstance(
            state_doc["SESSION_STATE"].get("Gates"), dict
        )

    def test_resets_when_p5_gates_open(self):
        """Resets to P5 when P5 gates are non-terminal in phase 6."""
        # Create mock evaluators that report an open gate
        def _mock_evaluate_p54_open(**kwargs) -> MockGateEvaluation:
            return MockGateEvaluation(gate_key="P5.4-BusinessRules", status="pending")

        open_gate_evaluators = GateEvaluators(
            evaluate_p53=_mock_evaluate_p53,
            evaluate_p54=_mock_evaluate_p54_open,
            evaluate_p55=_mock_evaluate_p55,
            evaluate_p56=_mock_evaluate_p56,
            phase_1_5_executed=_mock_phase_1_5_executed,
        )

        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
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
        normalize_phase6_p5_state(
            state_doc=state_doc,
            gate_constants=MOCK_GATE_CONSTANTS,
            gate_evaluators=open_gate_evaluators,
        )
        state = state_doc["SESSION_STATE"]

        # Should have reset to P5.4
        assert state["phase"] == "5.4-BusinessRules"
        assert state["phase6_state"] in ("", "6.none", "phase5_in_progress")
        assert state["implementation_review_complete"] is False
        assert "_p6_state_normalization" in state
        assert "P5.4-BusinessRules" in state["_p6_state_normalization"]["open_gates"]

    def test_no_action_when_all_gates_terminal(self):
        """No reset when all P5 gates are in terminal states."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
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
        normalize_phase6_p5_state(
            state_doc=state_doc,
            gate_constants=MOCK_GATE_CONSTANTS,
            gate_evaluators=MOCK_GATE_EVALUATORS,
        )
        state = state_doc["SESSION_STATE"]

        # Should remain in phase 6
        assert state["phase"] == "6-PostFlight"
        assert "_p6_state_normalization" not in state


class TestSyncConditionalP5GateStates:
    """Tests for sync_conditional_p5_gate_states."""

    def test_no_action_without_gates(self):
        """No changes when state has no Gates dict."""
        state_doc = {"SESSION_STATE": {}}
        sync_conditional_p5_gate_states(
            state_doc=state_doc,
            gate_evaluators=MOCK_GATE_EVALUATORS,
        )
        # Should not crash
        assert "Gates" not in state_doc["SESSION_STATE"]

    def test_no_action_when_gates_not_dict(self):
        """No changes when Gates is not a dict."""
        state_doc = {"SESSION_STATE": {"Gates": "not a dict"}}
        sync_conditional_p5_gate_states(
            state_doc=state_doc,
            gate_evaluators=MOCK_GATE_EVALUATORS,
        )
        assert state_doc["SESSION_STATE"]["Gates"] == "not a dict"
