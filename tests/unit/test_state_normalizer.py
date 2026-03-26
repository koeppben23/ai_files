"""Tests for StateNormalizer."""

from __future__ import annotations

import pytest

from governance_runtime.application.dto.canonical_state import CanonicalSessionState
from governance_runtime.application.services.state_normalizer import (
    get_all_gate_statuses,
    get_gate,
    is_gate_passed,
    is_gate_pending,
    normalize_to_canonical,
)


class TestNormalizeToCanonical:
    """Tests for normalize_to_canonical()."""

    def test_empty_state_returns_empty_canonical(self):
        """Empty input returns canonical state with empty nested blocks."""
        result = normalize_to_canonical({})
        # review_package and implementation_package are always present (may be empty)
        assert "review_package" in result
        assert "implementation_package" in result
        # Top-level fields should not be present
        assert "phase" not in result
        assert "gates" not in result

    def test_canonical_phase_field(self):
        """Canonical 'phase' field is resolved."""
        result = normalize_to_canonical({"phase": "6-PostFlight"})
        assert result["phase"] == "6-PostFlight"

    def test_legacy_Phase_field_resolved(self):
        """Legacy 'Phase' field is resolved to canonical 'phase'."""
        result = normalize_to_canonical({"phase": "5.4-BusinessRules"})
        assert result["phase"] == "5.4-BusinessRules"

    def test_canonical_takes_precedence_over_legacy(self):
        """Canonical field takes precedence when both exist."""
        # Test with both uppercase (legacy) and lowercase (canonical) keys
        result = normalize_to_canonical({"phase": "canonical", "Phase": "legacy"})
        assert result["phase"] == "canonical"

    def test_next_action_field(self):
        """next_action field is resolved from Next/next aliases."""
        result = normalize_to_canonical({"next": "continue"})
        assert result["next_action"] == "continue"

    def test_gates_normalized_with_canonical_keys(self):
        """Gates dict keys are normalized from hyphens/dots to underscores."""
        raw_state = {
            "Gates": {
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P6-ImplementationQA": "pending",
            }
        }
        result = normalize_to_canonical(raw_state)
        gates = result.get("gates", {})
        assert gates.get("P5_3_TestQuality") == "pass"
        assert gates.get("P5_4_BusinessRules") == "compliant"
        assert gates.get("P6_ImplementationQA") == "pending"
        # Legacy keys should not be present
        assert "P5.3-TestQuality" not in gates
        assert "P5.4-BusinessRules" not in gates

    def test_nested_implementation_review(self):
        """ImplementationReview block is normalized."""
        raw_state = {
            "ImplementationReview": {
                "iteration": 2,
                "max_iterations": 3,
                "implementation_review_complete": False,
            }
        }
        result = normalize_to_canonical(raw_state)
        review = result.get("implementation_review", {})
        assert review.get("iteration") == 2
        assert review.get("max_iterations") == 3
        assert review.get("implementation_review_complete") is False

    def test_p54_fields_flattened_to_nested(self):
        """p54_* fields are collected into p54 nested block."""
        raw_state = {
            "p54_evaluated_status": "compliant",
            "p54_invalid_rules": 0,
            "p54_reason_code": "P54-COMPLIANT",
        }
        result = normalize_to_canonical(raw_state)
        p54 = result.get("p54", {})
        assert p54.get("evaluated_status") == "compliant"
        assert p54.get("invalid_rules") == 0
        assert p54.get("reason_code") == "P54-COMPLIANT"
        # Original p54_* fields should not be in result
        assert "p54_evaluated_status" not in result

    def test_review_package_flattened(self):
        """review_package_* fields are collected into review_package nested block."""
        raw_state = {
            "review_package_ticket": "TICKET-123",
            "review_package_plan_body": "Some plan...",
            "review_package_presented": True,
        }
        result = normalize_to_canonical(raw_state)
        pkg = result.get("review_package", {})
        assert pkg.get("ticket") == "TICKET-123"
        assert pkg.get("plan_body") == "Some plan..."
        assert pkg.get("presented") is True

    def test_none_values_not_included(self):
        """None values are not included in canonical state."""
        # Test with both lowercase and uppercase keys, one with None
        raw_state = {"phase": "test", "Phase": None, "gates": None}
        result = normalize_to_canonical(raw_state)
        assert "phase" in result
        assert "gates" not in result

    def test_does_not_mutate_input(self):
        """Original state dict is not modified."""
        raw_state = {"phase": "test", "Gates": {"P5.3-TestQuality": "pass"}}
        original = dict(raw_state)
        original_gates = dict(raw_state["Gates"])
        normalize_to_canonical(raw_state)
        assert raw_state == original
        assert raw_state["Gates"] == original_gates


class TestGetGate:
    """Tests for get_gate()."""

    def test_get_by_canonical_name(self):
        """Get gate status by canonical name."""
        gates = {"P5_3_TestQuality": "pass", "P5_4_BusinessRules": "pending"}
        assert get_gate(gates, "P5_3_TestQuality") == "pass"

    def test_get_by_legacy_name(self):
        """Get gate status by legacy name (hyphens/dots)."""
        gates = {"P5_3_TestQuality": "pass"}
        assert get_gate(gates, "P5.3-TestQuality") == "pass"

    def test_returns_none_for_unknown(self):
        """Returns None for unknown gate."""
        gates = {"P5_3_TestQuality": "pass"}
        assert get_gate(gates, "UNKNOWN_GATE") is None


class TestIsGatePassed:
    """Tests for is_gate_passed()."""

    def test_approved_gate_is_passed(self):
        """Approved gate is passed."""
        gates = {"P5_Architecture": "approved"}
        assert is_gate_passed(gates, "P5_Architecture") is True

    def test_pass_gate_is_passed(self):
        """Pass gate is passed."""
        gates = {"P5_3_TestQuality": "pass"}
        assert is_gate_passed(gates, "P5_3_TestQuality") is True

    def test_pending_gate_is_not_passed(self):
        """Pending gate is not passed."""
        gates = {"P5_3_TestQuality": "pending"}
        assert is_gate_passed(gates, "P5_3_TestQuality") is False

    def test_unknown_gate_is_not_passed(self):
        """Unknown gate is not passed."""
        gates = {}
        assert is_gate_passed(gates, "UNKNOWN") is False


class TestIsGatePending:
    """Tests for is_gate_pending()."""

    def test_pending_gate(self):
        """Pending gate returns True."""
        gates = {"P5_3_TestQuality": "pending"}
        assert is_gate_pending(gates, "P5_3_TestQuality") is True

    def test_passed_gate(self):
        """Passed gate returns False."""
        gates = {"P5_3_TestQuality": "pass"}
        assert is_gate_pending(gates, "P5_3_TestQuality") is False

    def test_unknown_gate(self):
        """Unknown gate returns False."""
        gates = {}
        assert is_gate_pending(gates, "UNKNOWN") is False


class TestGetAllGateStatuses:
    """Tests for get_all_gate_statuses()."""

    def test_returns_copy_of_gates(self):
        """Returns dict copy of canonical gates."""
        gates = {"P5_3_TestQuality": "pass", "P5_4_BusinessRules": "pending"}
        result = get_all_gate_statuses(gates)
        assert result == gates
        assert result is not gates  # Different object
