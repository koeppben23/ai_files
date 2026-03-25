"""Phase 3: Guards Validation Tests (v3 - Unified model with strict validation)

Validiert die extrahierte guards.yaml Struktur mit strengen Regeln:
- Unified guard model (exit + transition with guard_type)
- Geschlossene, rekursiv validierte Guard-Grammatik
- Strikte Validierung gegen kaputte Bäume
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
RUNTIME_GUARD_FIELDS = {"id", "guard_type", "target", "event", "condition"}
NON_RUNTIME_GUARD_FIELDS = {"attributes", "description"}

# Valid guard types
VALID_GUARD_TYPES = {"exit", "transition"}

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

# Required keys per condition type (strict schema)
REQUIRED_KEYS_PER_TYPE = {
    "always": set(),
    "key_present": {"key"},
    "key_equals": {"key", "value"},
    "key_missing": {"key"},
    "numeric_gte": {"key", "threshold", "operator"},
    "all_of": {"operands"},
    "any_of": {"operands"},
}

# Allowed keys per condition type (closed schema)
ALLOWED_KEYS_PER_TYPE = {
    "always": {"type"},
    "key_present": {"type", "key"},
    "key_equals": {"type", "key", "value"},
    "key_missing": {"type", "key"},
    "numeric_gte": {"type", "key", "threshold", "operator"},
    "all_of": {"type", "operands"},
    "any_of": {"type", "operands"},
}

# Valid threshold types
VALID_THRESHOLD_TYPES = {"constant", "from_state"}

# Valid numeric operators
VALID_NUMERIC_OPERATORS = {"gte", "gt", "lte", "lt", "eq", "neq"}

# Max recursion depth to prevent stack overflow
MAX_CONDITION_DEPTH = 10


# ============================================================================
# Strict Recursive Condition Validator
# ============================================================================

def validate_condition_recursive(
    condition: Any, 
    path: str = "condition",
    depth: int = 0
) -> list[str]:
    """Recursively validate a condition node with strict checks.
    
    Returns list of error messages (empty if valid).
    """
    errors = []
    
    # Depth limit to prevent infinite recursion
    if depth > MAX_CONDITION_DEPTH:
        return [f"{path}: exceeded max recursion depth {MAX_CONDITION_DEPTH}"]
    
    # Must be a dict
    if not isinstance(condition, dict):
        return [f"{path}: must be a dict, got {type(condition).__name__}"]
    
    # Empty dict check
    if len(condition) == 0:
        return [f"{path}: must not be empty"]
    
    # Must have type
    if "type" not in condition:
        return [f"{path}: missing 'type' field"]
    
    cond_type = condition["type"]
    
    # Type must be valid
    if not isinstance(cond_type, str):
        return [f"{path}: 'type' must be string, got {type(cond_type).__name__}"]
    
    if cond_type not in VALID_CONDITION_TYPES:
        return [f"{path}: unknown type '{cond_type}'"]
    
    # Check for unknown keys (closed schema)
    allowed_keys = ALLOWED_KEYS_PER_TYPE[cond_type]
    unknown_keys = set(condition.keys()) - allowed_keys
    if unknown_keys:
        errors.append(f"{path}: unknown keys {sorted(unknown_keys)} for type '{cond_type}'")
    
    # Check for missing required keys
    required_keys = REQUIRED_KEYS_PER_TYPE[cond_type]
    missing_keys = required_keys - set(condition.keys())
    if missing_keys:
        errors.append(f"{path}: missing required keys {sorted(missing_keys)} for type '{cond_type}'")
    
    # Type-specific validation
    if cond_type == "always":
        pass  # No additional validation
    
    elif cond_type == "key_present":
        key = condition.get("key")
        if not isinstance(key, str):
            errors.append(f"{path}: 'key' must be string")
        elif len(key) == 0:
            errors.append(f"{path}: 'key' must not be empty")
    
    elif cond_type == "key_equals":
        key = condition.get("key")
        if not isinstance(key, str):
            errors.append(f"{path}: 'key' must be string")
        elif len(key) == 0:
            errors.append(f"{path}: 'key' must not be empty")
        # value can be any type
    
    elif cond_type == "key_missing":
        key = condition.get("key")
        if not isinstance(key, str):
            errors.append(f"{path}: 'key' must be string")
        elif len(key) == 0:
            errors.append(f"{path}: 'key' must not be empty")
    
    elif cond_type == "numeric_gte":
        key = condition.get("key")
        if not isinstance(key, str):
            errors.append(f"{path}: 'key' must be string")
        elif len(key) == 0:
            errors.append(f"{path}: 'key' must not be empty")
        
        operator = condition.get("operator")
        if not isinstance(operator, str):
            errors.append(f"{path}: 'operator' must be string")
        elif operator not in VALID_NUMERIC_OPERATORS:
            errors.append(f"{path}: invalid operator '{operator}', must be one of {sorted(VALID_NUMERIC_OPERATORS)}")
        
        threshold = condition.get("threshold")
        threshold_errors = _validate_threshold(threshold, f"{path}.threshold")
        errors.extend(threshold_errors)
    
    elif cond_type in ("all_of", "any_of"):
        operands = condition.get("operands")
        
        if not isinstance(operands, list):
            errors.append(f"{path}: 'operands' must be list")
        elif len(operands) == 0:
            errors.append(f"{path}: 'operands' must not be empty")
        else:
            # Check for mixed types (all operands should be conditions)
            for i, operand in enumerate(operands):
                if not isinstance(operand, dict):
                    errors.append(f"{path}.operands[{i}]: must be dict")
                elif "type" not in operand:
                    errors.append(f"{path}.operands[{i}]: missing 'type'")
                else:
                    # Recursively validate
                    operand_errors = validate_condition_recursive(
                        operand, f"{path}.operands[{i}]", depth + 1
                    )
                    errors.extend(operand_errors)
    
    return errors


def _validate_threshold(threshold: Any, path: str) -> list[str]:
    """Validate a threshold specification with strict checks."""
    errors = []
    
    if not isinstance(threshold, dict):
        return [f"{path}: must be a dict, got {type(threshold).__name__}"]
    
    if len(threshold) == 0:
        return [f"{path}: must not be empty"]
    
    if "type" not in threshold:
        return [f"{path}: missing 'type'"]
    
    thresh_type = threshold["type"]
    
    if not isinstance(thresh_type, str):
        return [f"{path}: 'type' must be string"]
    
    if thresh_type not in VALID_THRESHOLD_TYPES:
        return [f"{path}: unknown type '{thresh_type}', must be one of {sorted(VALID_THRESHOLD_TYPES)}"]
    
    # Check for unknown keys
    allowed_keys = {"type", "value", "key"}
    unknown_keys = set(threshold.keys()) - allowed_keys
    if unknown_keys:
        errors.append(f"{path}: unknown keys {sorted(unknown_keys)}")
    
    if thresh_type == "constant":
        if "value" not in threshold:
            errors.append(f"{path}: missing 'value' for constant threshold")
        else:
            value = threshold["value"]
            if not isinstance(value, (int, float)):
                errors.append(f"{path}: 'value' must be numeric, got {type(value).__name__}")
    
    elif thresh_type == "from_state":
        if "key" not in threshold:
            errors.append(f"{path}: missing 'key' for from_state threshold")
        else:
            key = threshold["key"]
            if not isinstance(key, str):
                errors.append(f"{path}: 'key' must be string")
            elif len(key) == 0:
                errors.append(f"{path}: 'key' must not be empty")
    
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
def all_guards(guards):
    """Extract all guards."""
    return guards.get("guards", [])


@pytest.fixture
def exit_guards(all_guards):
    """Extract exit guards."""
    return [g for g in all_guards if g.get("guard_type") == "exit"]


@pytest.fixture
def transition_guards(all_guards):
    """Extract transition guards."""
    return [g for g in all_guards if g.get("guard_type") == "transition"]


@pytest.fixture
def guard_ids(all_guards):
    """Extract all guard IDs."""
    return {g["id"] for g in all_guards}


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
        assert "guards" in guards
        assert isinstance(guards["guards"], list)

    def test_schema_is_guards_v1(self, guards):
        """Happy: Schema ist opencode.guards.v1."""
        assert guards["schema"] == "opencode.guards.v1"

    def test_has_guards(self, guards):
        """Happy: Guards vorhanden."""
        assert len(guards["guards"]) > 0

    def test_guard_ids_unique(self, all_guards):
        """Runtime: Guard IDs sind eindeutig."""
        ids = [g["id"] for g in all_guards]
        duplicates = [gid for gid in ids if ids.count(gid) > 1]
        assert not duplicates, f"Duplicate guard IDs: {set(duplicates)}"


@pytest.mark.governance
class TestGuardModel:
    """Unified Guard Model."""

    def test_all_guards_have_id(self, all_guards):
        """Runtime: Alle Guards haben ID."""
        for guard in all_guards:
            assert "id" in guard, f"Guard missing 'id'"
            assert isinstance(guard["id"], str), f"Guard id must be string"
            assert len(guard["id"]) > 0, f"Guard id must not be empty"

    def test_all_guards_have_guard_type(self, all_guards):
        """Runtime: Alle Guards haben guard_type."""
        for guard in all_guards:
            assert "guard_type" in guard, f"Guard {guard.get('id')} missing 'guard_type'"
            assert guard["guard_type"] in VALID_GUARD_TYPES, \
                f"Guard {guard.get('id')}: invalid guard_type '{guard['guard_type']}'"

    def test_all_guards_have_condition(self, all_guards):
        """Runtime: Alle Guards haben condition."""
        for guard in all_guards:
            assert "condition" in guard, f"Guard {guard.get('id')} missing 'condition'"

    def test_exit_guards_have_target(self, exit_guards):
        """Runtime: Exit Guards haben target (state_id)."""
        for guard in exit_guards:
            assert "target" in guard, f"Exit guard {guard.get('id')} missing 'target'"
            assert isinstance(guard["target"], str), f"Exit guard target must be string"

    def test_transition_guards_have_event(self, transition_guards):
        """Runtime: Transition Guards haben event."""
        for guard in transition_guards:
            assert "event" in guard, f"Transition guard {guard.get('id')} missing 'event'"
            assert isinstance(guard["event"], str), f"Transition guard event must be string"

    def test_transition_guard_events_unique(self, transition_guards):
        """Runtime: Transition Guard Events sind eindeutig."""
        events = [g["event"] for g in transition_guards]
        duplicates = [e for e in events if events.count(e) > 1]
        assert not duplicates, f"Duplicate guard events: {set(duplicates)}"

    def test_guard_attributes_are_non_runtime(self, all_guards):
        """Non-runtime: attributes ist optional und dokumentierend."""
        for guard in all_guards:
            if "attributes" in guard:
                attrs = guard["attributes"]
                assert isinstance(attrs, dict), f"Guard {guard.get('id')}: attributes must be dict"
                # attributes should not contain runtime logic
                for key in attrs:
                    assert key in {"description", "fail_mode", "contract_ref"}, \
                        f"Guard {guard.get('id')}: unknown attribute '{key}'"


@pytest.mark.governance
class TestConditionGrammar:
    """Closed Grammar Validation (ADR-002: structured, no DSL)."""

    def test_all_conditions_valid_type(self, all_guards):
        """Grammar: Alle Conditions haben gültigen Typ."""
        for guard in all_guards:
            condition = guard["condition"]
            assert isinstance(condition, dict), \
                f"Guard {guard['id']}: condition must be dict"
            assert "type" in condition, \
                f"Guard {guard['id']}: condition missing 'type'"
            assert condition["type"] in VALID_CONDITION_TYPES, \
                f"Guard {guard['id']}: unknown condition type '{condition['type']}'"

    def test_recursive_condition_validation(self, all_guards):
        """Grammar: Alle Conditions sind rekursiv valide."""
        all_errors = []
        for guard in all_guards:
            errors = validate_condition_recursive(guard["condition"], f"guard_{guard['id']}")
            all_errors.extend(errors)
        assert not all_errors, f"Condition validation errors:\n" + "\n".join(all_errors)


@pytest.mark.governance
class TestConditionNegative:
    """Negative Tests für kaputte Condition-Bäume."""

    def test_reject_empty_condition(self):
        """Negative: Empty condition dict wird abgelehnt."""
        errors = validate_condition_recursive({}, "test")
        assert any("must not be empty" in e for e in errors)

    def test_reject_condition_without_type(self):
        """Negative: Condition ohne type wird abgelehnt."""
        errors = validate_condition_recursive({"key": "foo"}, "test")
        assert any("missing 'type'" in e for e in errors)

    def test_reject_unknown_condition_type(self):
        """Negative: Unbekannter Condition-Type wird abgelehnt."""
        errors = validate_condition_recursive({"type": "unknown_type"}, "test")
        assert any("unknown type" in e for e in errors)

    def test_reject_always_with_extra_keys(self):
        """Negative: always mit extra keys wird abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "always", "extra": "field"}, 
            "test"
        )
        assert any("unknown keys" in e for e in errors)

    def test_reject_key_present_without_key(self):
        """Negative: key_present ohne key wird abgelehnt."""
        errors = validate_condition_recursive({"type": "key_present"}, "test")
        assert any("missing required keys" in e and "key" in e for e in errors)

    def test_reject_key_present_empty_key(self):
        """Negative: key_present mit leerem key wird abgelehnt."""
        errors = validate_condition_recursive({"type": "key_present", "key": ""}, "test")
        assert any("must not be empty" in e for e in errors)

    def test_reject_key_equals_without_value(self):
        """Negative: key_equals ohne value wird abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "key_equals", "key": "foo"}, 
            "test"
        )
        assert any("missing required keys" in e and "value" in e for e in errors)

    def test_reject_numeric_gte_without_threshold(self):
        """Negative: numeric_gte ohne threshold wird abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "numeric_gte", "key": "foo", "operator": "gte"}, 
            "test"
        )
        assert any("missing required keys" in e and "threshold" in e for e in errors)

    def test_reject_numeric_gte_invalid_operator(self):
        """Negative: numeric_gte mit ungültigem operator wird abgelehnt."""
        errors = validate_condition_recursive(
            {
                "type": "numeric_gte", 
                "key": "foo", 
                "operator": "invalid",
                "threshold": {"type": "constant", "value": 1}
            }, 
            "test"
        )
        assert any("invalid operator" in e for e in errors)

    def test_reject_numeric_gte_constant_non_numeric(self):
        """Negative: numeric_gte constant threshold nicht numerisch."""
        errors = validate_condition_recursive(
            {
                "type": "numeric_gte", 
                "key": "foo", 
                "operator": "gte",
                "threshold": {"type": "constant", "value": "not_a_number"}
            }, 
            "test"
        )
        assert any("'value' must be numeric" in e for e in errors)

    def test_reject_numeric_gte_unknown_threshold_type(self):
        """Negative: numeric_gte mit unbekanntem threshold type."""
        errors = validate_condition_recursive(
            {
                "type": "numeric_gte", 
                "key": "foo", 
                "operator": "gte",
                "threshold": {"type": "invalid_type", "value": 1}
            }, 
            "test"
        )
        assert any("unknown type" in e for e in errors)

    def test_reject_all_of_empty_operands(self):
        """Negative: all_of mit leeren operands wird abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "all_of", "operands": []}, 
            "test"
        )
        assert any("must not be empty" in e for e in errors)

    def test_reject_any_of_empty_operands(self):
        """Negative: any_of mit leeren operands wird abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "any_of", "operands": []}, 
            "test"
        )
        assert any("must not be empty" in e for e in errors)

    def test_reject_all_of_non_dict_operand(self):
        """Negative: all_of mit nicht-dict operand wird abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "all_of", "operands": ["not_a_dict"]}, 
            "test"
        )
        assert any("must be dict" in e for e in errors)

    def test_reject_nested_empty_operands(self):
        """Negative: Verschachtelte leere operands werden abgelehnt."""
        errors = validate_condition_recursive(
            {
                "type": "all_of", 
                "operands": [
                    {"type": "any_of", "operands": []}
                ]
            }, 
            "test"
        )
        assert any("must not be empty" in e for e in errors)

    def test_reject_unknown_key_in_leaf(self):
        """Negative: Unbekannte keys in leaf nodes werden abgelehnt."""
        errors = validate_condition_recursive(
            {"type": "key_present", "key": "foo", "unknown_field": "bar"}, 
            "test"
        )
        assert any("unknown keys" in e for e in errors)

    def test_reject_numeric_gte_threshold_unknown_keys(self):
        """Negative: Unbekannte keys in threshold werden abgelehnt."""
        errors = validate_condition_recursive(
            {
                "type": "numeric_gte", 
                "key": "foo", 
                "operator": "gte",
                "threshold": {"type": "constant", "value": 1, "extra": "field"}
            }, 
            "test"
        )
        assert any("unknown keys" in e for e in errors)


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

    def test_exit_guard_targets_match_topology(self, exit_guards):
        """Happy: Exit Guard Targets existieren in Topologie."""
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found for cross-reference")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        state_ids = {s["id"] for s in topology["states"]}
        
        for guard in exit_guards:
            assert guard["target"] in state_ids, \
                f"Exit guard {guard['id']} target '{guard['target']}' not in topology"
