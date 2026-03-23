"""Integration tests for the canonical state model.

These tests verify that the canonical state model works end-to-end:
- Legacy state with mixed field names → canonical state out
- Kernel code paths read canonical state correctly
- Round-trip scenarios work correctly
- Edge cases are handled properly
"""

from __future__ import annotations

import pytest

from governance_runtime.application.services.state_normalizer import (
    normalize_to_canonical,
    get_gate,
    is_gate_passed,
    is_gate_pending,
)
from governance_runtime.application.services.state_accessor import (
    get_phase,
    get_active_gate,
    get_status,
    get_next_gate_condition,
    get_mode,
    is_phase5_completed,
    is_workflow_complete,
    is_review_complete,
    get_review_iterations,
    get_max_review_iterations,
)


class TestCanonicalStateIntegration:
    """Test complete flow from legacy state to canonical state."""

    def test_legacy_pascal_case_phase_normalized(self):
        """Legacy PascalCase fields should normalize to snake_case."""
        legacy_state = {
            "Phase": "5-ArchitectureReview",
            "Next": "5.3",
            "Mode": "IN_PROGRESS",
            "active_gate": "Architecture Review Gate",
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["phase"] == "5-ArchitectureReview"
        assert canonical["next_action"] == "5.3"
        assert canonical["mode"] == "IN_PROGRESS"
        assert canonical["active_gate"] == "Architecture Review Gate"

    def test_legacy_snake_case_phase_preserved(self):
        """Existing snake_case fields should remain unchanged."""
        legacy_state = {
            "phase": "6-PostFlight",
            "next_action": "complete",
            "mode": "CLOSED",
            "active_gate": "none",
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["phase"] == "6-PostFlight"
        assert canonical["next_action"] == "complete"
        assert canonical["mode"] == "CLOSED"
        assert canonical["active_gate"] == "none"

    def test_mixed_legacy_fields_normalized(self):
        """Mixed legacy field names should all normalize correctly."""
        legacy_state = {
            "Phase": "4",
            "phase5_completed": True,
            "phase5_state": "phase5-in-progress",
            "Phase5State": "phase5-completed",
            "WorkflowComplete": True,
            "workflow_complete": False,
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["phase"] == "4"
        assert canonical["phase5_completed"] is True
        assert canonical["workflow_complete"] is False

    def test_gate_keys_with_hyphens_normalized(self):
        """Gate keys stored with hyphens/dots should normalize to underscores."""
        legacy_state = {
            "Gates": {
                "P5-Architecture": "pass",
                "P5.3-TestQuality": "pending",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
                "P5.6-RollbackSafety": "not-applicable",
            }
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["gates"]["P5_Architecture"] == "pass"
        assert canonical["gates"]["P5_3_TestQuality"] == "pending"
        assert canonical["gates"]["P5_4_BusinessRules"] == "compliant"
        assert canonical["gates"]["P5_5_TechnicalDebt"] == "approved"
        assert canonical["gates"]["P5_6_RollbackSafety"] == "not-applicable"

    def test_implementation_review_block_normalized(self):
        """ImplementationReview block should normalize correctly."""
        legacy_state = {
            "ImplementationReview": {
                "iteration": 3,
                "max_iterations": 5,
                "implementation_review_complete": True,
                "ImplementationReviewComplete": False,
            }
        }
        canonical = normalize_to_canonical(legacy_state)

        review = canonical["implementation_review"]
        assert review["iteration"] == 3
        assert review["max_iterations"] == 5
        assert review["implementation_review_complete"] is True

    def test_session_state_wrapper_handled(self):
        """State wrapped in SESSION_STATE should normalize correctly."""
        legacy_state = {
            "SESSION_STATE": {
                "Phase": "5",
                "Next": "5.3",
                "active_gate": "Test Quality Gate",
            }
        }
        # Simulate what get_canonical_state does
        state_obj = legacy_state.get("SESSION_STATE")
        raw_state = state_obj if isinstance(state_obj, dict) else legacy_state
        canonical = normalize_to_canonical(raw_state)

        assert canonical["phase"] == "5"
        assert canonical["next_action"] == "5.3"
        assert canonical["active_gate"] == "Test Quality Gate"

    def test_empty_state_returns_empty_canonical(self):
        """Empty state should return mostly empty canonical state."""
        canonical = normalize_to_canonical({})
        # Normalizer returns empty nested blocks for packages
        assert canonical.get("phase") is None
        assert "review_package" in canonical or canonical == {}

    def test_partial_legacy_state_normalizes_known_fields(self):
        """Partial legacy state should normalize known fields, ignore unknown."""
        legacy_state = {
            "Phase": "6",
            "unknown_field": "should be ignored",
            "another_unknown": 123,
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["phase"] == "6"
        assert "unknown_field" not in canonical
        assert "another_unknown" not in canonical


class TestGateHelpersIntegration:
    """Test gate helper functions with various gate key formats."""

    def test_get_gate_by_canonical_key(self):
        """Get gate status using canonical underscore key."""
        canonical = normalize_to_canonical({
            "Gates": {
                "P5.3-TestQuality": "pass",
            }
        })
        assert get_gate(canonical["gates"], "P5_3_TestQuality") == "pass"

    def test_get_gate_by_legacy_key(self):
        """Get gate status using legacy hyphen/dot key."""
        canonical = normalize_to_canonical({
            "Gates": {
                "P5.4-BusinessRules": "compliant",
            }
        })
        # After normalization, canonical keys exist
        assert get_gate(canonical["gates"], "P5_4_BusinessRules") == "compliant"
        # get_gate also supports lookup via GATE_KEY_ALIASES reverse mapping
        assert get_gate(canonical["gates"], "P5.4-BusinessRules") == "compliant"

    def test_is_gate_passed_with_various_statuses(self):
        """is_gate_passed correctly identifies terminal passed states."""
        canonical = normalize_to_canonical({
            "Gates": {
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant-with-exceptions",
                "P5.5-TechnicalDebt": "approved",
                "P5.6-RollbackSafety": "not-applicable",
                "P5-Architecture": "pending",
            }
        })

        assert is_gate_passed(canonical["gates"], "P5_3_TestQuality") is True
        assert is_gate_passed(canonical["gates"], "P5_4_BusinessRules") is True
        assert is_gate_passed(canonical["gates"], "P5_5_TechnicalDebt") is True
        assert is_gate_passed(canonical["gates"], "P5_6_RollbackSafety") is True
        assert is_gate_passed(canonical["gates"], "P5_Architecture") is False

    def test_is_gate_pending_correctly(self):
        """is_gate_pending correctly identifies pending gates."""
        canonical = normalize_to_canonical({
            "Gates": {
                "P5.3-TestQuality": "pending",
                "P5.4-BusinessRules": "pass",
            }
        })

        assert is_gate_pending(canonical["gates"], "P5_3_TestQuality") is True
        assert is_gate_pending(canonical["gates"], "P5_4_BusinessRules") is False


class TestStateAccessorIntegration:
    """Test state_accessor with various input formats."""

    def test_accessor_with_legacy_pascal_case(self):
        """State accessor should resolve legacy PascalCase fields."""
        legacy_state = {"Phase": "5-ArchitectureReview"}
        assert get_phase(legacy_state) == "5-ArchitectureReview"

    def test_accessor_with_canonical_snake_case(self):
        """State accessor should work with canonical snake_case."""
        canonical_state = {"phase": "6-PostFlight"}
        assert get_phase(canonical_state) == "6-PostFlight"

    def test_accessor_returns_empty_for_missing_fields(self):
        """State accessor should return empty string for missing fields."""
        state = {}
        assert get_phase(state) == ""
        assert get_active_gate(state) == ""
        assert get_status(state) == ""
        assert get_mode(state) == ""

    def test_accessor_phase5_completed_with_legacy_key(self):
        """phase5_completed should resolve correctly."""
        assert is_phase5_completed({"phase5_completed": True}) is True
        assert is_phase5_completed({"phase5_completed": False}) is False
        assert is_phase5_completed({}) is False

    def test_accessor_workflow_complete_with_legacy_key(self):
        """workflow_complete should resolve correctly."""
        assert is_workflow_complete({"workflow_complete": True}) is True
        assert is_workflow_complete({"WorkflowComplete": True}) is True
        assert is_workflow_complete({}) is False

    def test_accessor_review_iterations(self):
        """Review iterations should resolve correctly."""
        assert get_review_iterations({"phase6_review_iterations": 5}) == 5
        assert get_review_iterations({}) == 0

    def test_accessor_max_review_iterations(self):
        """Max review iterations should resolve correctly."""
        assert get_max_review_iterations({"phase6_max_review_iterations": 10}) == 10
        assert get_max_review_iterations({}) == 0


class TestRoundTripScenarios:
    """Test realistic round-trip scenarios from persisted state."""

    def test_phase5_architecture_review_roundtrip(self):
        """Simulate a Phase 5 Architecture Review session state."""
        persisted_state = {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "Next": "5",
                "phase": "5-ArchitectureReview",
                "next": "5",
                "active_gate": "Architecture Review Gate",
                "next_gate_condition": "Run /continue to proceed to P5.3",
                "status": "OK",
                "Mode": "IN_PROGRESS",
                "phase5_completed": False,
                "Gates": {
                    "P5-Architecture": "pass",
                    "P5.3-TestQuality": "pending",
                },
            }
        }

        # Simulate get_canonical_state
        state_obj = persisted_state.get("SESSION_STATE")
        raw = state_obj if isinstance(state_obj, dict) else persisted_state
        canonical = normalize_to_canonical(raw)

        # Verify canonical form
        assert canonical["phase"] == "5-ArchitectureReview"
        assert canonical["next_action"] == "5"
        assert canonical["active_gate"] == "Architecture Review Gate"
        assert canonical["status"] == "OK"
        assert canonical["mode"] == "IN_PROGRESS"
        assert canonical["phase5_completed"] is False
        assert canonical["gates"]["P5_Architecture"] == "pass"
        assert canonical["gates"]["P5_3_TestQuality"] == "pending"

        # Verify gate helpers work
        assert is_gate_passed(canonical["gates"], "P5_Architecture") is True
        assert is_gate_pending(canonical["gates"], "P5_3_TestQuality") is True

    def test_phase6_implementation_review_roundtrip(self):
        """Simulate a Phase 6 Implementation Review session state."""
        persisted_state = {
            "SESSION_STATE": {
                "phase": "6",
                "next_action": "complete",
                "active_gate": "Implementation Presentation Gate",
                "status": "OK",
                "mode": "IN_PROGRESS",
                "phase5_completed": True,
                "phase6_review_iterations": 3,
                "phase6_max_review_iterations": 5,
                "ImplementationReview": {
                    "iteration": 3,
                    "max_iterations": 5,
                    "implementation_review_complete": True,
                },
                "Gates": {
                    "P5-Architecture": "pass",
                    "P5.3-TestQuality": "pass",
                    "P5.4-BusinessRules": "compliant",
                    "P5.5-TechnicalDebt": "approved",
                    "P5.6-RollbackSafety": "not-applicable",
                },
            }
        }

        state_obj = persisted_state.get("SESSION_STATE")
        raw = state_obj if isinstance(state_obj, dict) else persisted_state
        canonical = normalize_to_canonical(raw)

        # Verify canonical form
        assert canonical["phase"] == "6"
        assert canonical["phase5_completed"] is True
        assert is_review_complete(persisted_state["SESSION_STATE"]) is True
        assert get_review_iterations(persisted_state["SESSION_STATE"]) == 3
        assert get_max_review_iterations(persisted_state["SESSION_STATE"]) == 5

        # All P5 gates should be passed
        gates = canonical["gates"]
        assert is_gate_passed(gates, "P5_Architecture") is True
        assert is_gate_passed(gates, "P5_3_TestQuality") is True
        assert is_gate_passed(gates, "P5_4_BusinessRules") is True
        assert is_gate_passed(gates, "P5_5_TechnicalDebt") is True
        assert is_gate_passed(gates, "P5_6_RollbackSafety") is True

    def test_kernel_reads_canonical_state(self):
        """Simulate kernel code reading canonical state."""
        session_state = {
            "Phase": "5",
            "Next": "5.3",
            "active_gate": "Test Quality Gate",
            "next_gate_condition": "Complete test quality gate",
            "phase5_completed": False,
        }

        # Kernel code path: normalize first, then read
        canonical = normalize_to_canonical(session_state)

        # Kernel decisions based on canonical state
        phase = canonical["phase"]
        next_token = canonical["next_action"]
        gate = canonical["active_gate"]

        # Simulate simple routing logic
        if phase.startswith("5"):
            if gate == "Test Quality Gate":
                assert next_token == "5.3"

        # Gate evaluation
        assert is_phase5_completed(session_state) is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_none_values_not_included(self):
        """None values should not be included in canonical state."""
        legacy_state = {
            "Phase": None,
            "phase": "5",
            "Next": None,
        }
        canonical = normalize_to_canonical(legacy_state)
        assert "Phase" not in canonical
        assert canonical["phase"] == "5"
        assert "next_action" not in canonical

    def test_empty_string_not_treated_as_none(self):
        """Empty strings should be preserved."""
        legacy_state = {
            "phase": "",
            "active_gate": "",
        }
        canonical = normalize_to_canonical(legacy_state)
        assert canonical["phase"] == ""
        assert canonical["active_gate"] == ""

    def test_numeric_values_preserved(self):
        """Numeric values should be preserved correctly."""
        legacy_state = {
            "phase6_review_iterations": 5,
            "phase6_max_review_iterations": 10,
            "phase6_min_review_iterations": 2,
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["phase6_review_iterations"] == 5
        assert canonical["phase6_max_review_iterations"] == 10
        assert canonical["phase6_min_review_iterations"] == 2

    def test_boolean_values_preserved(self):
        """Boolean values should be preserved correctly."""
        legacy_state = {
            "phase5_completed": True,
            "implementation_review_complete": False,
            "workflow_complete": True,
        }
        canonical = normalize_to_canonical(legacy_state)

        assert canonical["phase5_completed"] is True
        assert canonical["implementation_review_complete"] is False
        assert canonical["workflow_complete"] is True

    def test_does_not_mutate_input(self):
        """normalize_to_canonical should not mutate the input."""
        original = {
            "Phase": "5",
            "Unknown": "value",
        }
        original_copy = dict(original)

        normalize_to_canonical(original)

        assert original == original_copy
