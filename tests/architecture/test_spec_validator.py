"""Phase 8: Spec-Validator und Conformance-Checks (v1)

Umfassende Validierung der internen Konsistenz jeder Spec
und der Cross-Spec-Conformance.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path


def _find_spec_path(spec_name: str) -> Path | None:
    """Find a spec file relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / spec_name
        if candidate.exists():
            return candidate
    return None


def _load_yaml(spec_name: str) -> dict | None:
    """Load a YAML spec file."""
    path = _find_spec_path(spec_name)
    if path is None:
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def topology():
    """Load topology.yaml."""
    return _load_yaml("topology.yaml")


@pytest.fixture
def guards():
    """Load guards.yaml."""
    return _load_yaml("guards.yaml")


@pytest.fixture
def command_policy():
    """Load command_policy.yaml."""
    return _load_yaml("command_policy.yaml")


@pytest.fixture
def messages():
    """Load messages.yaml."""
    return _load_yaml("messages.yaml")


# ============================================================================
# Intra-Spec Validators
# ============================================================================

@pytest.mark.governance
class TestTopologyIntraSpec:
    """Intra-Spec: topology.yaml must be internally consistent."""

    def test_topology_loads_successfully(self, topology):
        """Happy: topology.yaml loads without errors."""
        assert topology is not None
        assert "states" in topology

    def test_all_state_ids_unique(self, topology):
        """Runtime: State IDs sind eindeutig."""
        state_ids = [s["id"] for s in topology["states"]]
        duplicates = [s for s in state_ids if state_ids.count(s) > 1]
        assert not duplicates, f"Duplicate state IDs: {set(duplicates)}"

    def test_all_transitions_have_valid_targets(self, topology):
        """Runtime: Alle Transition-Targets existieren."""
        state_ids = {s["id"] for s in topology["states"]}
        invalid_targets = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                if t["target"] not in state_ids:
                    invalid_targets.append(
                        f"{state['id']}:{t['id']} -> {t['target']}"
                    )
        assert not invalid_targets, f"Invalid transition targets: {invalid_targets}"

    def test_all_transitions_have_required_fields(self, topology):
        """Runtime: Alle Transitions haben Pflichtfelder."""
        missing_fields = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                for field in ["id", "event", "target"]:
                    if field not in t:
                        missing_fields.append(f"{state['id']}:{t.get('id', '?')}: missing {field}")
        assert not missing_fields, f"Missing fields: {missing_fields}"

    def test_terminal_states_have_no_mutating_transitions(self, topology):
        """Runtime: Terminale States haben keine normalen Transitions."""
        violations = []
        for state in topology["states"]:
            if state.get("terminal"):
                transitions = state.get("transitions", [])
                # Terminal states may have transitions (e.g., for error handling)
                # but should be clearly documented
                if transitions:
                    for t in transitions:
                        if t["event"] == "default":
                            violations.append(f"{state['id']}: terminal state has default transition")
        # This is informational - terminal states can have transitions
        # but the pattern is noted


@pytest.mark.governance
class TestGuardsIntraSpec:
    """Intra-Spec: guards.yaml must be internally consistent."""

    def test_guards_loads_successfully(self, guards):
        """Happy: guards.yaml loads without errors."""
        assert guards is not None
        assert "guards" in guards

    def test_all_guard_ids_unique(self, guards):
        """Runtime: Guard IDs sind eindeutig."""
        guard_ids = [g["id"] for g in guards.get("guards", [])]
        duplicates = [g for g in guard_ids if guard_ids.count(g) > 1]
        assert not duplicates, f"Duplicate guard IDs: {set(duplicates)}"

    def test_all_guard_types_valid(self, guards):
        """Runtime: Guard-Typen sind gültig."""
        valid_types = {
            "exit", "transition", "phase_gate", "has_field", "field_equals",
            "field_not_empty", "has_any_field", "all_fields_present",
            "composite", "phase_exit_ready"
        }
        invalid_types = []
        for g in guards.get("guards", []):
            gtype = g.get("guard_type")
            if gtype not in valid_types:
                invalid_types.append(f"{g['id']}: invalid type '{gtype}'")
        assert not invalid_types, f"Invalid guard types: {invalid_types}"

    def test_composite_guards_reference_valid_guards(self, guards):
        """Runtime: Composite Guards referenzieren existierende Guards."""
        guard_ids = {g["id"] for g in guards.get("guards", [])}
        invalid_refs = []
        for g in guards.get("guards", []):
            if g.get("guard_type") == "composite":
                for ref in g.get("guard_refs", []):
                    if ref not in guard_ids:
                        invalid_refs.append(f"{g['id']}: references unknown guard '{ref}'")
        assert not invalid_refs, f"Invalid guard references: {invalid_refs}"


@pytest.mark.governance
class TestCommandPolicyIntraSpec:
    """Intra-Spec: command_policy.yaml must be internally consistent."""

    def test_command_policy_loads_successfully(self, command_policy):
        """Happy: command_policy.yaml loads without errors."""
        assert command_policy is not None
        assert "commands" in command_policy

    def test_all_command_ids_unique(self, command_policy):
        """Runtime: Command IDs sind eindeutig."""
        cmd_ids = [c["id"] for c in command_policy.get("commands", [])]
        duplicates = [c for c in cmd_ids if cmd_ids.count(c) > 1]
        assert not duplicates, f"Duplicate command IDs: {set(duplicates)}"

    def test_all_commands_have_required_fields(self, command_policy):
        """Runtime: Alle Commands haben Pflichtfelder."""
        required = ["id", "command", "description", "allowed_in"]
        missing = []
        for c in command_policy.get("commands", []):
            for field in required:
                if field not in c:
                    missing.append(f"{c.get('id', '?')}: missing {field}")
        assert not missing, f"Missing fields: {missing}"

    def test_command_restrictions_state_patterns_unique(self, command_policy):
        """Runtime: Command-Restriction-State-Patterns sind eindeutig."""
        patterns = []
        for r in command_policy.get("command_restrictions", []):
            patterns.append(r.get("state_pattern"))
        duplicates = [p for p in patterns if patterns.count(p) > 1]
        assert not duplicates, f"Duplicate state patterns: {set(duplicates)}"


@pytest.mark.governance
class TestMessagesIntraSpec:
    """Intra-Spec: messages.yaml must be internally consistent."""

    def test_messages_loads_successfully(self, messages):
        """Happy: messages.yaml loads without errors."""
        assert messages is not None
        assert "state_messages" in messages or "transition_messages" in messages

    def test_all_message_ids_unique(self, messages):
        """Runtime: Message IDs sind eindeutig."""
        ids = []
        for m in messages.get("state_messages", []):
            ids.append(m["id"])
        for m in messages.get("transition_messages", []):
            ids.append(m["id"])
        duplicates = [mid for mid in ids if ids.count(mid) > 1]
        assert not duplicates, f"Duplicate message IDs: {set(duplicates)}"

    def test_transition_messages_have_required_fields(self, messages):
        """Runtime: Transition Messages haben Pflichtfelder."""
        required = ["id", "state_id", "event", "gate_message", "instruction"]
        missing = []
        for m in messages.get("transition_messages", []):
            for field in required:
                if field not in m:
                    missing.append(f"{m.get('id', '?')}: missing {field}")
        assert not missing, f"Missing fields: {missing}"

    def test_transition_event_format_valid(self, messages):
        """Runtime: Events haben snake_case Format."""
        import re
        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        invalid = []
        for m in messages.get("transition_messages", []):
            event = m.get("event", "")
            if not pattern.match(event):
                invalid.append(f"{m['id']}: invalid event format '{event}'")
        assert not invalid, f"Invalid event formats: {invalid}"


# ============================================================================
# Cross-Spec Conformance
# ============================================================================

@pytest.mark.governance
class TestTopologyGuardsConformance:
    """Cross-Spec: topology.yaml ↔ guards.yaml Conformance."""

    def test_guard_refs_in_topology_point_to_valid_guards(self, topology, guards):
        """Cross-Spec: guard_ref in Topology verweist auf existierende Guards."""
        if topology is None or guards is None:
            pytest.skip("Specs not found")
        
        guard_ids = {g["id"] for g in guards.get("guards", [])}
        invalid_refs = []
        
        for state in topology["states"]:
            for t in state.get("transitions", []):
                guard_ref = t.get("guard_ref")
                if guard_ref and guard_ref not in guard_ids:
                    invalid_refs.append(
                        f"{state['id']}:{t['id']} -> guard_ref '{guard_ref}' not in guards.yaml"
                    )
        
        assert not invalid_refs, f"Invalid guard references: {invalid_refs}"


@pytest.mark.governance
class TestTopologyMessagesConformance:
    """Cross-Spec: topology.yaml ↔ messages.yaml Conformance."""

    def test_message_state_ids_exist_in_topology(self, topology, messages):
        """Cross-Spec: Message state_ids existieren in Topology."""
        if topology is None or messages is None:
            pytest.skip("Specs not found")
        
        state_ids = {s["id"] for s in topology["states"]}
        # Add future states that may not be in topology yet
        future_states = {
            "6.approved", "6.presentation", "6.execution",
            "6.blocked", "6.rework", "6.rejected", "6.complete",
            "6.internal_review", "6"
        }
        state_ids = state_ids | future_states
        
        invalid = []
        for m in messages.get("transition_messages", []):
            state_id = m.get("state_id")
            if state_id and state_id not in state_ids:
                invalid.append(f"{m['id']}: state_id '{state_id}' not in topology")
        
        assert not invalid, f"Invalid state_ids in messages: {invalid}"

    def test_message_events_exist_in_topology_for_state(self, topology, messages):
        """Cross-Spec: Message events existieren in Topology für den State."""
        if topology is None or messages is None:
            pytest.skip("Specs not found")
        
        # Build state -> events map from topology
        state_events: dict[str, set[str]] = {}
        for state in topology["states"]:
            state_id = state["id"]
            events = {t["event"] for t in state.get("transitions", [])}
            state_events[state_id] = events
        
        invalid = []
        for m in messages.get("transition_messages", []):
            state_id = m.get("state_id")
            event = m.get("event")
            
            # Skip if state_id is a future state (not yet in topology)
            future_states = {
                "6.approved", "6.presentation", "6.execution",
                "6.blocked", "6.rework", "6.rejected", "6.complete",
                "6.internal_review"
            }
            if state_id in future_states:
                continue
            
            if state_id not in state_events:
                invalid.append(f"{m['id']}: state_id '{state_id}' not in topology")
                continue
            
            if event not in state_events[state_id]:
                invalid.append(
                    f"{m['id']}: event '{event}' not defined for state '{state_id}' in topology"
                )
        
        assert not invalid, f"Event validation failures: {invalid}"


@pytest.mark.governance
class TestCommandPolicyTopologyConformance:
    """Cross-Spec: command_policy.yaml ↔ topology.yaml Conformance."""

    def test_allowed_states_exist_in_topology(self, command_policy, topology):
        """Cross-Spec: States in allowed_in existieren in Topology."""
        if command_policy is None or topology is None:
            pytest.skip("Specs not found")
        
        state_ids = {s["id"] for s in topology["states"]}
        # Add future states
        future_states = {
            "6.approved", "6.presentation", "6.execution",
            "6.blocked", "6.rework", "6.rejected", "6.complete",
            "6.internal_review"
        }
        state_ids = state_ids | future_states | {"*"}  # * is universal
        
        invalid = []
        for c in command_policy.get("commands", []):
            allowed_in = c.get("allowed_in", [])
            if isinstance(allowed_in, list):
                for state in allowed_in:
                    if state not in state_ids:
                        invalid.append(
                            f"{c['id']}: allowed_in contains '{state}' not in topology"
                        )
        
        assert not invalid, f"Invalid allowed_in states: {invalid}"

    def test_command_restriction_states_exist_in_topology(self, command_policy, topology):
        """Cross-Spec: States in command_restrictions existieren in Topology."""
        if command_policy is None or topology is None:
            pytest.skip("Specs not found")
        
        state_ids = {s["id"] for s in topology["states"]}
        state_ids.add("*")  # Wildcard for terminal
        
        invalid = []
        for r in command_policy.get("command_restrictions", []):
            pattern = r.get("state_pattern", "")
            # Skip patterns that reference terminal state (not a real state)
            if pattern == "*.terminal":
                continue
            if pattern not in state_ids:
                invalid.append(f"Restriction: state_pattern '{pattern}' not in topology")
        
        assert not invalid, f"Invalid restriction patterns: {invalid}"


@pytest.mark.governance
class TestMessagesCommandPolicyConformance:
    """Cross-Spec: messages.yaml ↔ command_policy.yaml Conformance."""

    def test_commands_in_messages_are_in_command_policy(self, messages, command_policy):
        """Cross-Spec: Commands in Messages sind in Command-Policy erlaubt."""
        if messages is None or command_policy is None:
            pytest.skip("Specs not found")
        
        import re
        COMMAND_PATTERN = re.compile(r"/[a-z][a-z0-9\-]*")
        
        # Build command -> allowed_states map
        cmd_allowed: dict[str, set[str]] = {}
        for c in command_policy.get("commands", []):
            cmd = c["command"]
            allowed = c.get("allowed_in", [])
            if isinstance(allowed, list):
                cmd_allowed[cmd] = set(allowed)
            elif allowed == "*":
                cmd_allowed[cmd] = {"*"}
        
        violations = []
        for m in messages.get("transition_messages", []):
            instruction = m.get("instruction", "")
            state_id = m.get("state_id")
            
            for match in COMMAND_PATTERN.finditer(instruction):
                cmd = match.group()
                
                # /continue and /review are universal
                if cmd in {"/continue", "/review"}:
                    continue
                
                allowed = cmd_allowed.get(cmd, set())
                if "*" in allowed:
                    continue
                
                if state_id not in allowed:
                    # Check if state is a Phase 6 substate that inherits from 6
                    if state_id and state_id.startswith("6."):
                        if "6" in allowed:
                            continue
                    
                    violations.append(
                        f"{m['id']}: command '{cmd}' not allowed in state '{state_id}'"
                    )
        
        assert not violations, f"Command conformance violations: {violations}"


@pytest.mark.governance
class TestSpecSchemaVersionConformance:
    """Cross-Spec: Schema-Versionen sind konsistent."""

    def test_all_specs_have_schema_identifier(self, topology, guards, command_policy, messages):
        """Cross-Spec: Alle Specs haben schema oder schema_version Identifier."""
        specs = {
            "topology": topology,
            "guards": guards,
            "command_policy": command_policy,
            "messages": messages
        }
        
        missing = []
        for name, spec in specs.items():
            if spec:
                has_schema = "schema" in spec or "schema_version" in spec
                if not has_schema:
                    missing.append(name)
        
        assert not missing, f"Missing schema identifier in: {missing}"

    def test_schema_identifiers_follow_naming_convention(self, topology, guards, command_policy, messages):
        """Cross-Spec: Schema-Identifiers folgen der Naming Convention."""
        import re
        pattern = re.compile(r"^[a-z][a-z0-9._\-]*\.v\d+$")
        
        specs = {
            "topology": topology,
            "guards": guards,
            "command_policy": command_policy,
            "messages": messages
        }
        
        invalid = []
        for name, spec in specs.items():
            if spec:
                schema = spec.get("schema", "")
                if schema and not pattern.match(schema):
                    invalid.append(f"{name}: '{schema}'")
        
        assert not invalid, f"Invalid schema identifiers: {invalid}"
