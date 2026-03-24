"""Phase 3: Guards Validation Tests

Validiert die extrahierte guards.yaml Struktur:
- Alle Exit Guards haben State-IDs und required_keys
- Alle Transition Guards haben ID, Event und Condition
- Guard-Struktur ist konsistent mit ADR-002 (strukturiert, kein DSL)
- Condition-Types sind gültig
- Event-Namen sind konsistent mit Topologie

Diese Tests laufen GEGEN die extrahierte guards.yaml.
"""

from __future__ import annotations

import re
import pytest
import yaml
from pathlib import Path
from typing import Any


# ============================================================================
# Valid Condition Types (ADR-002: structured, no DSL)
# ============================================================================

VALID_CONDITION_TYPES = {
    "always",           # Always true (for default)
    "state_check",      # Check state key
    "derived",          # Derived from evaluator function
    "composite",        # Composite (and/or/not)
}

VALID_OPERATORS = {
    "equals", "not_equals",
    "truthy", "falsy",
    "missing", "missing_or_empty",
    "less_than", "greater_than",
    "contains",
    "and", "or", "not",
}


# ============================================================================
# Fixtures
# ============================================================================

def _find_guards_path() -> Path | None:
    """Find guards.yaml relative to test file location.
    
    Returns None if not found - caller should handle the case.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "guards.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def guards_path():
    """Provides the guards path, skipping test if not found."""
    path = _find_guards_path()
    if path is None:
        pytest.skip("guards.yaml not found - test requires guards file")
    return path


@pytest.fixture
def guards(guards_path):
    """Lädt die guards.yaml für Struktur-Tests."""
    with open(guards_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def exit_guards(guards):
    """Extract exit guards."""
    return guards.get("exit_guards", [])


@pytest.fixture
def transition_guards(guards):
    """Extract transition guards."""
    return guards.get("transition_guards", [])


@pytest.fixture
def guard_ids(transition_guards):
    """Extract all guard IDs."""
    return {g["id"] for g in transition_guards}


@pytest.fixture
def guard_events(transition_guards):
    """Extract all guard events."""
    return {g["event"] for g in transition_guards}


# ============================================================================
# Test Classes
# ============================================================================

@pytest.mark.governance
class TestGuardsStructure:
    """Grundlegende Guards-Struktur."""

    def test_guards_loads_successfully(self, guards):
        """Happy: Guards lädt erfolgreich."""
        assert "version" in guards
        assert "schema" in guards
        assert "exit_guards" in guards
        assert "transition_guards" in guards
        assert isinstance(guards["exit_guards"], list)
        assert isinstance(guards["transition_guards"], list)

    def test_schema_is_guards_v1(self, guards):
        """Happy: Schema ist opencode.guards.v1."""
        assert guards["schema"] == "opencode.guards.v1"

    def test_has_exit_guards(self, guards):
        """Happy: Exit Guards vorhanden."""
        assert len(guards["exit_guards"]) > 0

    def test_has_transition_guards(self, guards):
        """Happy: Transition Guards vorhanden."""
        assert len(guards["transition_guards"]) > 0


@pytest.mark.governance
class TestExitGuards:
    """Exit Guards (Strict Exit Gates)."""

    def test_exit_guards_have_state_id(self, exit_guards):
        """Happy: Alle Exit Guards haben state_id."""
        for guard in exit_guards:
            assert "state_id" in guard, f"Exit guard missing 'state_id'"
            assert isinstance(guard["state_id"], str), \
                f"Exit guard state_id must be string"

    def test_exit_guards_have_required_keys(self, exit_guards):
        """Happy: Alle Exit Guards haben required_keys."""
        for guard in exit_guards:
            assert "required_keys" in guard, \
                f"Exit guard for {guard.get('state_id')} missing 'required_keys'"
            assert isinstance(guard["required_keys"], list), \
                f"Exit guard required_keys must be list"
            assert len(guard["required_keys"]) > 0, \
                f"Exit guard for {guard.get('state_id')} has empty required_keys"

    def test_exit_guards_required_keys_are_strings(self, exit_guards):
        """Happy: Alle required_keys sind nicht-leere Strings."""
        for guard in exit_guards:
            for key in guard["required_keys"]:
                assert isinstance(key, str) and key.strip(), \
                    f"Exit guard {guard.get('state_id')}: invalid key '{key}'"

    def test_exit_guards_have_description(self, exit_guards):
        """Happy: Alle Exit Guards haben description."""
        for guard in exit_guards:
            assert "description" in guard, \
                f"Exit guard for {guard.get('state_id')} missing 'description'"
            assert isinstance(guard["description"], str), \
                f"Exit guard description must be string"

    def test_exit_guards_state_ids_unique(self, exit_guards):
        """Happy: Exit Guard State-IDs sind eindeutig."""
        state_ids = [g["state_id"] for g in exit_guards]
        duplicates = [sid for sid in state_ids if state_ids.count(sid) > 1]
        assert not duplicates, f"Duplicate exit guard state IDs: {set(duplicates)}"


@pytest.mark.governance
class TestTransitionGuards:
    """Transition Guards (Condition Selectors)."""

    def test_transition_guards_have_id(self, transition_guards):
        """Happy: Alle Transition Guards haben ID."""
        for guard in transition_guards:
            assert "id" in guard, f"Transition guard missing 'id'"
            assert isinstance(guard["id"], str), \
                f"Transition guard id must be string"
            assert guard["id"].startswith("guard_"), \
                f"Transition guard ID should start with 'guard_'"

    def test_transition_guards_have_event(self, transition_guards):
        """Happy: Alle Transition Guards haben Event."""
        for guard in transition_guards:
            assert "event" in guard, f"Transition guard {guard.get('id')} missing 'event'"
            assert isinstance(guard["event"], str), \
                f"Transition guard event must be string"

    def test_transition_guards_have_condition(self, transition_guards):
        """Happy: Alle Transition Guards haben Condition."""
        for guard in transition_guards:
            assert "condition" in guard, \
                f"Transition guard {guard.get('id')} missing 'condition'"
            assert isinstance(guard["condition"], dict), \
                f"Transition guard condition must be dict"

    def test_transition_guards_condition_has_type(self, transition_guards):
        """Happy: Alle Conditions haben einen gültigen Typ."""
        for guard in transition_guards:
            condition = guard["condition"]
            assert "type" in condition, \
                f"Guard {guard.get('id')} condition missing 'type'"
            assert condition["type"] in VALID_CONDITION_TYPES, \
                f"Guard {guard.get('id')} has invalid condition type: {condition['type']}"

    def test_guard_ids_unique(self, transition_guards):
        """Happy: Guard IDs sind eindeutig."""
        ids = [g["id"] for g in transition_guards]
        duplicates = [gid for gid in ids if ids.count(gid) > 1]
        assert not duplicates, f"Duplicate guard IDs: {set(duplicates)}"

    def test_guard_events_unique(self, transition_guards):
        """Happy: Guard Events sind eindeutig (1:1 Mapping)."""
        events = [g["event"] for g in transition_guards]
        duplicates = [e for e in events if events.count(e) > 1]
        assert not duplicates, f"Duplicate guard events: {set(duplicates)}"


@pytest.mark.governance
class TestGuardConditions:
    """Guard Condition Structure (ADR-002: structured, no DSL)."""

    def test_always_condition_structure(self, transition_guards):
        """Happy: 'always' conditions haben keine weiteren Felder."""
        for guard in transition_guards:
            if guard["condition"]["type"] == "always":
                # 'always' should only have type
                allowed_keys = {"type"}
                extra_keys = set(guard["condition"].keys()) - allowed_keys
                assert not extra_keys, \
                    f"Guard {guard['id']}: 'always' condition has extra keys: {extra_keys}"

    def test_state_check_condition_structure(self, transition_guards):
        """Happy: 'state_check' conditions haben key und operator."""
        for guard in transition_guards:
            if guard["condition"]["type"] == "state_check":
                condition = guard["condition"]
                assert "key" in condition, \
                    f"Guard {guard['id']}: state_check missing 'key'"
                assert "operator" in condition, \
                    f"Guard {guard['id']}: state_check missing 'operator'"
                assert condition["operator"] in VALID_OPERATORS, \
                    f"Guard {guard['id']}: invalid operator '{condition['operator']}'"

    def test_derived_condition_structure(self, transition_guards):
        """Happy: 'derived' conditions haben evaluator und expected."""
        for guard in transition_guards:
            if guard["condition"]["type"] == "derived":
                condition = guard["condition"]
                assert "evaluator" in condition, \
                    f"Guard {guard['id']}: derived missing 'evaluator'"
                assert "expected" in condition, \
                    f"Guard {guard['id']}: derived missing 'expected'"
                assert isinstance(condition["expected"], bool), \
                    f"Guard {guard['id']}: derived expected must be boolean"

    def test_composite_condition_structure(self, transition_guards):
        """Happy: 'composite' conditions haben operator und operands."""
        for guard in transition_guards:
            if guard["condition"]["type"] == "composite":
                condition = guard["condition"]
                assert "operator" in condition, \
                    f"Guard {guard['id']}: composite missing 'operator'"
                assert condition["operator"] in {"and", "or", "not"}, \
                    f"Guard {guard['id']}: composite operator must be and/or/not"
                assert "operands" in condition, \
                    f"Guard {guard['id']}: composite missing 'operands'"
                assert isinstance(condition["operands"], list), \
                    f"Guard {guard['id']}: composite operands must be list"

    def test_no_dsl_in_conditions(self, transition_guards):
        """ADR-002: Keine DSL in Conditions (nur strukturierte Syntax)."""
        import json
        for guard in transition_guards:
            condition_str = json.dumps(guard["condition"])
            # Check for DSL-like patterns
            assert "=>" not in condition_str, \
                f"Guard {guard['id']}: contains DSL arrow '=>'"
            assert "lambda" not in condition_str, \
                f"Guard {guard['id']}: contains 'lambda'"
            assert "fn(" not in condition_str, \
                f"Guard {guard['id']}: contains function call syntax"


@pytest.mark.governance
class TestGuardTopologyConsistency:
    """Konsistenz zwischen Guards und Topologie."""

    def test_default_guard_exists(self, guard_events):
        """Happy: 'default' guard existiert."""
        assert "default" in guard_events, "Missing default guard"

    def test_guard_events_match_topology_transitions(self, guard_events):
        """Happy: Guard-Events sind konsistent mit Topologie-Transitions."""
        # Events from topology (from test_topology.py known conditions)
        topology_events = {
            "default",
            "ticket_present",
            "business_rules_execute",
            "no_apis",
            "plan_record_missing",
            "self_review_iterations_pending",
            "self_review_iterations_met",
            "business_rules_gate_required",
            "technical_debt_proposed",
            "rollback_required",
            "implementation_accepted",
            "implementation_blocked",
            "implementation_rework_clarification_pending",
            "implementation_presentation_ready",
            "implementation_execution_in_progress",
            "implementation_started",
            "workflow_approved",
            "review_changes_requested",
            "rework_clarification_pending",
            "review_rejected",
            "implementation_review_pending",
            "implementation_review_complete",
        }
        
        # All guard events should be in topology events
        extra_events = guard_events - topology_events
        assert not extra_events, \
            f"Guard events not in topology: {extra_events}"

    def test_exit_guard_state_ids_match_topology(self, exit_guards):
        """Happy: Exit Guard State-IDs existieren in Topologie."""
        # Load topology to check
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found for cross-reference")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        state_ids = {s["id"] for s in topology["states"]}
        
        for guard in exit_guards:
            assert guard["state_id"] in state_ids, \
                f"Exit guard state_id '{guard['state_id']}' not in topology"


def _find_topology_path() -> Path | None:
    """Find topology.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "topology.yaml"
        if candidate.exists():
            return candidate
    return None
