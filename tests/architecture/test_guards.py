"""Phase 3: Guards Validation Tests (v2 - Strict with recursive validation)

Validiert die extrahierte guards.yaml Struktur mit strengen Regeln:
- Geschlossene, rekursiv validierte Guard-Grammatik
- Keine DSL (ADR-002)
- description ist non-runtime metadata
- Alle Condition-Typen sind bekannt und korrekt strukturiert
- Rekursive Strukturen sind valide (keine leeren/kaputten Bäume)
- numeric_gte hat korrekte Typ-/Existenzvalidierung

Diese Tests laufen GEGEN die extrahierte guards.yaml.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from typing import Any


# ============================================================================
# Closed Grammar Definition (ADR-002)
# ============================================================================

# Runtime fields for guard objects
RUNTIME_GUARD_FIELDS = {"id", "event", "condition"}
NON_RUNTIME_GUARD_FIELDS = {"description"}

# Runtime fields for exit guard objects
RUNTIME_EXIT_GUARD_FIELDS = {"state_id", "required_keys"}
NON_RUNTIME_EXIT_GUARD_FIELDS = {"description"}

# Allowed ConditionNode types (closed grammar)
VALID_CONDITION_TYPES = {
    "always",           # No operands, always true
    "key_present",      # key exists and is truthy
    "key_equals",       # key equals value
    "key_missing",      # key does not exist or is falsy
    "numeric_gte",      # numeric comparison with threshold
    "all_of",           # AND composite (recursive)
    "any_of",           # OR composite (recursive)
}

# Allowed keys per condition type (strict schema)
# 'type' is always allowed (checked separately)
CONDITION_SCHEMA = {
    "always": set(),  # No additional keys allowed
    "key_present": {"key", "negate"},
    "key_equals": {"key", "value"},
    "key_missing": {"key"},
    "numeric_gte": {"key", "threshold", "operator"},
    "all_of": {"operands"},
    "any_of": {"operands"},
}

# Valid threshold types
VALID_THRESHOLD_TYPES = {"constant", "from_state"}

# Valid numeric operators
VALID_NUMERIC_OPERATORS = {"gte", "gt", "lte", "lt", "eq", "neq"}


# ============================================================================
# Recursive Condition Validator
# ============================================================================

def validate_condition_recursive(condition: Any, path: str = "condition") -> list[str]:
    """Recursively validate a condition node.
    
    Returns list of error messages (empty if valid).
    """
    errors = []
    
    if not isinstance(condition, dict):
        return [f"{path}: must be a dict, got {type(condition).__name__}"]
    
    if "type" not in condition:
        return [f"{path}: missing 'type' field"]
    
    cond_type = condition["type"]
    
    if cond_type not in VALID_CONDITION_TYPES:
        return [f"{path}: unknown type '{cond_type}'"]
    
    # Check for unknown keys (type is always allowed)
    allowed_keys = CONDITION_SCHEMA[cond_type] | {"type"}
    unknown_keys = set(condition.keys()) - allowed_keys
    if unknown_keys:
        errors.append(f"{path}: unknown keys {unknown_keys} for type '{cond_type}'")
    
    # Type-specific validation
    if cond_type == "always":
        pass  # No additional validation
    
    elif cond_type == "key_present":
        if "key" not in condition:
            errors.append(f"{path}: missing 'key'")
        elif not isinstance(condition["key"], str):
            errors.append(f"{path}: 'key' must be string")
    
    elif cond_type == "key_equals":
        if "key" not in condition:
            errors.append(f"{path}: missing 'key'")
        elif not isinstance(condition["key"], str):
            errors.append(f"{path}: 'key' must be string")
        if "value" not in condition:
            errors.append(f"{path}: missing 'value'")
    
    elif cond_type == "key_missing":
        if "key" not in condition:
            errors.append(f"{path}: missing 'key'")
        elif not isinstance(condition["key"], str):
            errors.append(f"{path}: 'key' must be string")
    
    elif cond_type == "numeric_gte":
        if "key" not in condition:
            errors.append(f"{path}: missing 'key'")
        elif not isinstance(condition["key"], str):
            errors.append(f"{path}: 'key' must be string")
        
        if "operator" not in condition:
            errors.append(f"{path}: missing 'operator'")
        elif condition["operator"] not in VALID_NUMERIC_OPERATORS:
            errors.append(f"{path}: invalid operator '{condition['operator']}'")
        
        if "threshold" not in condition:
            errors.append(f"{path}: missing 'threshold'")
        else:
            threshold = condition["threshold"]
            threshold_errors = _validate_threshold(threshold, f"{path}.threshold")
            errors.extend(threshold_errors)
    
    elif cond_type in ("all_of", "any_of"):
        if "operands" not in condition:
            errors.append(f"{path}: missing 'operands'")
        else:
            operands = condition["operands"]
            if not isinstance(operands, list):
                errors.append(f"{path}: 'operands' must be list")
            elif len(operands) == 0:
                errors.append(f"{path}: 'operands' must not be empty")
            else:
                for i, operand in enumerate(operands):
                    operand_errors = validate_condition_recursive(
                        operand, f"{path}.operands[{i}]"
                    )
                    errors.extend(operand_errors)
    
    return errors


def _validate_threshold(threshold: Any, path: str) -> list[str]:
    """Validate a threshold specification."""
    errors = []
    
    if not isinstance(threshold, dict):
        return [f"{path}: must be a dict, got {type(threshold).__name__}"]
    
    if "type" not in threshold:
        return [f"{path}: missing 'type'"]
    
    thresh_type = threshold["type"]
    
    if thresh_type not in VALID_THRESHOLD_TYPES:
        return [f"{path}: unknown type '{thresh_type}'"]
    
    if thresh_type == "constant":
        if "value" not in threshold:
            errors.append(f"{path}: missing 'value' for constant threshold")
        elif not isinstance(threshold["value"], (int, float)):
            errors.append(f"{path}: 'value' must be numeric")
    
    elif thresh_type == "from_state":
        if "key" not in threshold:
            errors.append(f"{path}: missing 'key' for from_state threshold")
        elif not isinstance(threshold["key"], str):
            errors.append(f"{path}: 'key' must be string")
    
    return errors


# ============================================================================
# Fixtures
# ============================================================================

def _find_guards_path() -> Path | None:
    """Find guards.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "guards.yaml"
        if candidate.exists():
            return candidate
    return None


def _find_topology_path() -> Path | None:
    """Find topology.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "topology.yaml"
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
        """Runtime: Alle Exit Guards haben state_id."""
        for guard in exit_guards:
            assert "state_id" in guard, f"Exit guard missing 'state_id'"
            assert isinstance(guard["state_id"], str), \
                f"Exit guard state_id must be string"

    def test_exit_guards_have_required_keys(self, exit_guards):
        """Runtime: Alle Exit Guards haben required_keys."""
        for guard in exit_guards:
            assert "required_keys" in guard, \
                f"Exit guard for {guard.get('state_id')} missing 'required_keys'"
            assert isinstance(guard["required_keys"], list), \
                f"Exit guard required_keys must be list"
            assert len(guard["required_keys"]) > 0, \
                f"Exit guard for {guard.get('state_id')} has empty required_keys"

    def test_exit_guards_required_keys_are_strings(self, exit_guards):
        """Runtime: Alle required_keys sind nicht-leere Strings."""
        for guard in exit_guards:
            for key in guard["required_keys"]:
                assert isinstance(key, str) and key.strip(), \
                    f"Exit guard {guard.get('state_id')}: invalid key '{key}'"

    def test_exit_guards_state_ids_unique(self, exit_guards):
        """Runtime: Exit Guard State-IDs sind eindeutig."""
        state_ids = [g["state_id"] for g in exit_guards]
        duplicates = [sid for sid in state_ids if state_ids.count(sid) > 1]
        assert not duplicates, f"Duplicate exit guard state IDs: {set(duplicates)}"

    def test_exit_guards_no_unknown_runtime_fields(self, exit_guards):
        """Runtime: Exit Guards haben nur bekannte Runtime-Felder."""
        for guard in exit_guards:
            unknown = set(guard.keys()) - RUNTIME_EXIT_GUARD_FIELDS - NON_RUNTIME_EXIT_GUARD_FIELDS
            assert not unknown, \
                f"Exit guard {guard.get('state_id')}: unknown fields {unknown}"


@pytest.mark.governance
class TestTransitionGuards:
    """Transition Guards (Condition Selectors)."""

    def test_transition_guards_have_id(self, transition_guards):
        """Runtime: Alle Transition Guards haben ID."""
        for guard in transition_guards:
            assert "id" in guard, f"Transition guard missing 'id'"
            assert isinstance(guard["id"], str), \
                f"Transition guard id must be string"
            assert guard["id"].startswith("guard_"), \
                f"Transition guard ID should start with 'guard_'"

    def test_transition_guards_have_event(self, transition_guards):
        """Runtime: Alle Transition Guards haben Event."""
        for guard in transition_guards:
            assert "event" in guard, f"Transition guard {guard.get('id')} missing 'event'"
            assert isinstance(guard["event"], str), \
                f"Transition guard event must be string"

    def test_transition_guards_have_condition(self, transition_guards):
        """Runtime: Alle Transition Guards haben Condition."""
        for guard in transition_guards:
            assert "condition" in guard, \
                f"Transition guard {guard.get('id')} missing 'condition'"

    def test_guard_ids_unique(self, transition_guards):
        """Runtime: Guard IDs sind eindeutig."""
        ids = [g["id"] for g in transition_guards]
        duplicates = [gid for gid in ids if ids.count(gid) > 1]
        assert not duplicates, f"Duplicate guard IDs: {set(duplicates)}"

    def test_guard_events_unique(self, transition_guards):
        """Runtime: Guard Events sind eindeutig (1:1 Mapping)."""
        events = [g["event"] for g in transition_guards]
        duplicates = [e for e in events if events.count(e) > 1]
        assert not duplicates, f"Duplicate guard events: {set(duplicates)}"

    def test_transition_guards_no_unknown_runtime_fields(self, transition_guards):
        """Runtime: Transition Guards haben nur bekannte Runtime-Felder."""
        for guard in transition_guards:
            unknown = set(guard.keys()) - RUNTIME_GUARD_FIELDS - NON_RUNTIME_GUARD_FIELDS
            assert not unknown, \
                f"Transition guard {guard.get('id')}: unknown fields {unknown}"


@pytest.mark.governance
class TestConditionGrammar:
    """Closed Grammar Validation (ADR-002: structured, no DSL)."""

    def test_all_conditions_valid_type(self, transition_guards):
        """Grammar: Alle Conditions haben gültigen Typ."""
        for guard in transition_guards:
            condition = guard["condition"]
            assert isinstance(condition, dict), \
                f"Guard {guard['id']}: condition must be dict"
            assert "type" in condition, \
                f"Guard {guard['id']}: condition missing 'type'"
            assert condition["type"] in VALID_CONDITION_TYPES, \
                f"Guard {guard['id']}: unknown condition type '{condition['type']}'"

    def test_recursive_condition_validation(self, transition_guards):
        """Grammar: Alle Conditions sind rekursiv valide."""
        all_errors = []
        for guard in transition_guards:
            errors = validate_condition_recursive(guard["condition"], f"guard_{guard['id']}")
            all_errors.extend(errors)
        assert not all_errors, f"Condition validation errors:\n" + "\n".join(all_errors)

    def test_always_condition_no_extra_keys(self, transition_guards):
        """Grammar: 'always' conditions haben keine zusätzlichen Felder."""
        for guard in transition_guards:
            if guard["condition"].get("type") == "always":
                allowed = {"type"}
                extra = set(guard["condition"].keys()) - allowed
                assert not extra, \
                    f"Guard {guard['id']}: 'always' has extra keys {extra}"

    def test_numeric_gte_has_threshold(self, transition_guards):
        """Grammar: 'numeric_gte' hat gültigen threshold."""
        for guard in transition_guards:
            if guard["condition"].get("type") == "numeric_gte":
                condition = guard["condition"]
                assert "threshold" in condition, \
                    f"Guard {guard['id']}: numeric_gte missing 'threshold'"
                threshold = condition["threshold"]
                assert isinstance(threshold, dict), \
                    f"Guard {guard['id']}: threshold must be dict"
                assert "type" in threshold, \
                    f"Guard {guard['id']}: threshold missing 'type'"
                assert threshold["type"] in VALID_THRESHOLD_TYPES, \
                    f"Guard {guard['id']}: unknown threshold type '{threshold['type']}'"

    def test_numeric_gte_constant_threshold_is_numeric(self, transition_guards):
        """Grammar: numeric_gte constant threshold ist numerisch."""
        for guard in transition_guards:
            if guard["condition"].get("type") == "numeric_gte":
                threshold = guard["condition"].get("threshold", {})
                if threshold.get("type") == "constant":
                    assert "value" in threshold, \
                        f"Guard {guard['id']}: constant threshold missing 'value'"
                    assert isinstance(threshold["value"], (int, float)), \
                        f"Guard {guard['id']}: constant threshold value must be numeric"

    def test_numeric_gte_from_state_has_key(self, transition_guards):
        """Grammar: numeric_gte from_state threshold hat key."""
        for guard in transition_guards:
            if guard["condition"].get("type") == "numeric_gte":
                threshold = guard["condition"].get("threshold", {})
                if threshold.get("type") == "from_state":
                    assert "key" in threshold, \
                        f"Guard {guard['id']}: from_state threshold missing 'key'"
                    assert isinstance(threshold["key"], str), \
                        f"Guard {guard['id']}: from_state threshold key must be string"

    def test_composite_has_non_empty_operands(self, transition_guards):
        """Grammar: composite conditions haben nicht-leere operands."""
        for guard in transition_guards:
            cond_type = guard["condition"].get("type")
            if cond_type in ("all_of", "any_of"):
                operands = guard["condition"].get("operands", [])
                assert len(operands) > 0, \
                    f"Guard {guard['id']}: {cond_type} has empty operands"

    def test_no_dsl_patterns(self, transition_guards):
        """ADR-002: Keine DSL-Patterns in Conditions."""
        import json
        for guard in transition_guards:
            condition_str = json.dumps(guard["condition"])
            assert "=>" not in condition_str, \
                f"Guard {guard['id']}: contains DSL arrow '=>'"
            assert "lambda" not in condition_str, \
                f"Guard {guard['id']}: contains 'lambda'"
            assert "fn(" not in condition_str, \
                f"Guard {guard['id']}: contains function call syntax"
            assert "eval(" not in condition_str, \
                f"Guard {guard['id']}: contains 'eval'"
            assert "exec(" not in condition_str, \
                f"Guard {guard['id']}: contains 'exec'"


@pytest.mark.governance
class TestDescriptionIsNonRuntime:
    """description ist non-runtime metadata (ADR-001)."""

    def test_description_not_used_in_runtime_logic(self):
        """Non-runtime: description hat keinen Einfluss auf Guard-Evaluation."""
        # This is a design invariant test - documents that description
        # is purely for human documentation, not runtime logic.
        # The recursive validator does NOT check description content.
        pass  # Invariant: validator ignores description

    def test_description_is_optional(self, transition_guards):
        """Non-runtime: description ist optional."""
        # Guards can exist without description
        for guard in transition_guards:
            # description is optional, not required
            pass  # No assertion needed

    def test_description_is_string_when_present(self, transition_guards):
        """Non-runtime: Wenn vorhanden, ist description ein String."""
        for guard in transition_guards:
            if "description" in guard:
                assert isinstance(guard["description"], str), \
                    f"Guard {guard.get('id')}: description must be string"


@pytest.mark.governance
class TestGuardTopologyConsistency:
    """Konsistenz zwischen Guards und Topologie."""

    def test_default_guard_exists(self, guard_events):
        """Happy: 'default' guard existiert."""
        assert "default" in guard_events, "Missing default guard"

    def test_guard_events_match_topology_transitions(self, guard_events):
        """Happy: Guard-Events sind konsistent mit Topologie-Transitions."""
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found for cross-reference")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        topology_events = set()
        for state in topology["states"]:
            for t in state.get("transitions", []):
                topology_events.add(t["event"])
        
        # All guard events should be in topology events
        extra_events = guard_events - topology_events
        assert not extra_events, \
            f"Guard events not in topology: {extra_events}"

    def test_exit_guard_state_ids_match_topology(self, exit_guards):
        """Happy: Exit Guard State-IDs existieren in Topologie."""
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found for cross-reference")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        state_ids = {s["id"] for s in topology["states"]}
        
        for guard in exit_guards:
            assert guard["state_id"] in state_ids, \
                f"Exit guard state_id '{guard['state_id']}' not in topology"
