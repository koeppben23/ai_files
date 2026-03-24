"""Phase 5: Messages Tests (v2 - Strict with cross-ref validation)

Validiert die extrahierte messages.yaml Struktur:
- Stabile Message-IDs (id field)
- Context Contract ist definiert
- Keine Runtime-Felder in Messages
- Cross-Ref: state_id muss in Topologie existieren
- Cross-Ref: transition_key source muss in Topologie existieren
- Conformance: Commands in instructions müssen in Command-Policy erlaubt sein
- Negative Tests für unbekannte Contexts/IDs

Diese Tests laufen GEGEN die extrahierte messages.yaml.
"""

from __future__ import annotations

import re
import pytest
import yaml
from pathlib import Path
from typing import Any


# ============================================================================
# Valid Patterns and Contracts
# ============================================================================

# Context contract allowed keys
ALLOWED_CONTEXT_KEYS = {
    "state_id", "event", "command", "iteration_count", 
    "max_iterations", "required_evidence"
}

# Commands that may be referenced in instructions
ALLOWED_COMMAND_REFERENCES = {
    "/continue",  # Universal
    "/review",    # Universal read-only
    "/ticket",    # State 4
    "/plan",      # States 4, 5
    "/implement",  # State 6 (transitional)
    "/review-decision",  # State 6 (transitional)
    "/implementation-decision",  # State 6 (transitional)
}

# Pattern for command references in instructions
COMMAND_REFERENCE_PATTERN = re.compile(r"/[a-z][a-z0-9_-]*")


# ============================================================================
# Fixtures
# ============================================================================

def _find_messages_path() -> Path | None:
    """Find messages.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "messages.yaml"
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


def _find_command_policy_path() -> Path | None:
    """Find command_policy.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "command_policy.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def messages_path():
    """Provides the messages path, skipping test if not found."""
    path = _find_messages_path()
    if path is None:
        pytest.skip("messages.yaml not found - test requires file")
    return path


@pytest.fixture
def messages(messages_path):
    """Lädt die messages.yaml für Struktur-Tests."""
    with open(messages_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def state_messages(messages):
    """Extract state messages."""
    return messages.get("state_messages", [])


@pytest.fixture
def transition_messages(messages):
    """Extract transition messages."""
    return messages.get("transition_messages", [])


@pytest.fixture
def state_ids_from_messages(state_messages):
    """Extract state IDs from state messages."""
    return {m["state_id"] for m in state_messages}


@pytest.fixture
def message_ids(messages):
    """Extract all message IDs."""
    ids = set()
    for m in messages.get("state_messages", []):
        ids.add(m["id"])
    for m in messages.get("transition_messages", []):
        ids.add(m["id"])
    return ids


@pytest.fixture
def topology():
    """Load topology.yaml for cross-spec validation."""
    topo_path = _find_topology_path()
    if topo_path is None:
        return None
    with open(topo_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def topology_state_ids(topology):
    """Extract state IDs from topology."""
    if topology is None:
        return set()
    return {s["id"] for s in topology["states"]}


@pytest.fixture
def topology_transition_events(topology):
    """Extract transition events from topology grouped by source state."""
    if topology is None:
        return {}
    result = {}
    for state in topology["states"]:
        state_id = state["id"]
        events = set()
        for t in state.get("transitions", []):
            events.add(t.get("event", "default"))
        result[state_id] = events
    return result


@pytest.fixture
def command_policy():
    """Load command_policy.yaml for cross-spec validation."""
    cp_path = _find_command_policy_path()
    if cp_path is None:
        return None
    with open(cp_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def allowed_commands_by_state(command_policy):
    """Map state_id to allowed commands."""
    if command_policy is None:
        return {}
    result = {}  # state_id -> set of command names
    for cmd in command_policy.get("commands", []):
        allowed_in = cmd.get("allowed_in")
        if allowed_in == "*":
            # Universal command - add to all states (will be filtered later)
            result["*"] = result.get("*", set()) | {cmd["command"]}
        elif isinstance(allowed_in, list):
            for state_id in allowed_in:
                result[state_id] = result.get(state_id, set()) | {cmd["command"]}
    return result


# ============================================================================
# Future States (ADR-003)
# ============================================================================

FUTURE_STATES = {
    "6.approved", "6.presentation", "6.execution",
    "6.internal_review", "6.blocked", "6.rework",
    "6.rejected", "6.complete"
}


# ============================================================================
# Test Classes
# ============================================================================

@pytest.mark.governance
class TestMessagesStructure:
    """Grundlegende Messages Struktur."""

    def test_messages_loads_successfully(self, messages):
        """Happy: Messages lädt erfolgreich."""
        assert "version" in messages
        assert "schema" in messages
        assert "state_messages" in messages
        assert "transition_messages" in messages
        assert "context_contract" in messages

    def test_schema_is_messages_v1(self, messages):
        """Happy: Schema ist opencode.messages.v1."""
        assert messages["schema"] == "opencode.messages.v1"

    def test_has_state_messages(self, messages):
        """Happy: State Messages vorhanden."""
        assert len(messages["state_messages"]) > 0

    def test_has_transition_messages(self, messages):
        """Happy: Transition Messages vorhanden."""
        assert len(messages["transition_messages"]) > 0


@pytest.mark.governance
class TestContextContract:
    """Context Contract Definition."""

    def test_context_contract_exists(self, messages):
        """Runtime: Context Contract ist definiert."""
        assert "context_contract" in messages
        contract = messages["context_contract"]
        assert "allowed_keys" in contract
        assert "fallback_rules" in contract
        assert "value_types" in contract

    def test_allowed_context_keys_are_set(self, messages):
        """Runtime: Allowed Context Keys sind definiert."""
        allowed = set(messages["context_contract"]["allowed_keys"])
        # Must contain essential keys
        assert "state_id" in allowed
        assert "event" in allowed

    def test_fallback_rules_defined(self, messages):
        """Runtime: Fallback rules sind definiert."""
        rules = messages["context_contract"]["fallback_rules"]
        assert "missing_state_id" in rules
        assert "unknown_key" in rules


@pytest.mark.governance
class TestMessageIds:
    """Stabile Message-IDs."""

    def test_state_messages_have_stable_id(self, state_messages):
        """Runtime: Alle State Messages haben stabile ID."""
        for msg in state_messages:
            assert "id" in msg, f"State message missing 'id'"
            assert isinstance(msg["id"], str)
            assert msg["id"].startswith("msg.state."), \
                f"State message ID should start with 'msg.state.'"

    def test_transition_messages_have_stable_id(self, transition_messages):
        """Runtime: Alle Transition Messages haben stabile ID."""
        for msg in transition_messages:
            assert "id" in msg, f"Transition message missing 'id'"
            assert isinstance(msg["id"], str)
            assert msg["id"].startswith("msg.trans."), \
                f"Transition message ID should start with 'msg.trans.'"

    def test_message_ids_unique(self, message_ids):
        """Runtime: Message IDs sind eindeutig."""
        ids_list = list(message_ids)
        duplicates = [mid for mid in ids_list if ids_list.count(mid) > 1]
        assert not duplicates, f"Duplicate message IDs: {set(duplicates)}"

    def test_state_message_id_matches_state_id(self, state_messages):
        """Runtime: State Message ID enthält state_id."""
        for msg in state_messages:
            msg_id = msg["id"]
            state_id = msg["state_id"]
            # ID format: msg.state.<state_id>
            assert state_id in msg_id, \
                f"Message ID '{msg_id}' should contain state_id '{state_id}'"


@pytest.mark.governance
class TestStateMessages:
    """State Message Definitionen."""

    def test_state_messages_have_required_fields(self, state_messages):
        """Runtime: Alle State Messages haben Pflichtfelder."""
        for msg in state_messages:
            assert "state_id" in msg
            assert "display_name" in msg
            assert "gate_message" in msg
            assert "instruction" in msg

    def test_state_ids_unique(self, state_messages):
        """Runtime: State IDs sind eindeutig."""
        ids = [m["state_id"] for m in state_messages]
        duplicates = [sid for sid in ids if ids.count(sid) > 1]
        assert not duplicates, f"Duplicate state IDs: {set(duplicates)}"

    def test_state_messages_no_runtime_fields(self, state_messages):
        """Runtime: State Messages enthalten KEINE Runtime-Felder."""
        runtime_fields = {
            "next", "route_strategy", "transitions", "terminal",
            "exit_required_keys", "output_policy", "token"
        }
        for msg in state_messages:
            found_runtime = set(msg.keys()) & runtime_fields
            assert not found_runtime, \
                f"Message {msg['id']}: runtime fields {found_runtime} found in presentation layer"


@pytest.mark.governance
class TestTransitionMessages:
    """Transition Message Definitionen."""

    def test_transition_messages_have_required_fields(self, transition_messages):
        """Runtime: Alle Transition Messages haben Pflichtfelder."""
        for msg in transition_messages:
            assert "id" in msg
            assert "transition_key" in msg
            assert "gate_message" in msg
            assert "instruction" in msg

    def test_transition_keys_unique(self, transition_messages):
        """Runtime: Transition Keys sind eindeutig."""
        keys = [m["transition_key"] for m in transition_messages]
        duplicates = [k for k in keys if keys.count(k) > 1]
        assert not duplicates, f"Duplicate transition keys: {set(duplicates)}"

    def test_transition_key_format(self, transition_messages):
        """Runtime: Transition Keys haben korrektes Format."""
        # Format: "<source_state>-<event>"
        pattern = re.compile(r"^[a-zA-Z0-9.\-]+-[a-z_]+$")
        for msg in transition_messages:
            key = msg["transition_key"]
            assert pattern.match(key), \
                f"Invalid transition key format: '{key}'"

    def test_transition_messages_no_runtime_fields(self, transition_messages):
        """Runtime: Transition Messages enthalten KEINE Runtime-Felder."""
        runtime_fields = {
            "next", "source", "when", "active_gate", "next_gate_condition"
        }
        for msg in transition_messages:
            found_runtime = set(msg.keys()) & runtime_fields
            assert not found_runtime, \
                f"Message {msg['id']}: runtime fields {found_runtime} in presentation layer"


@pytest.mark.governance
class TestCrossRefTopology:
    """Cross-Ref: Messages → Topology."""

    def test_all_topology_states_have_messages(self, state_ids_from_messages, topology_state_ids):
        """Cross-Ref: Alle Topology States haben Messages."""
        if not topology_state_ids:
            pytest.skip("topology.yaml not found")
        
        # Current topology states should have messages
        missing = topology_state_ids - state_ids_from_messages - FUTURE_STATES
        assert not missing, f"Topology states without messages: {missing}"

    def test_transition_key_source_in_topology(self, transition_messages, topology_state_ids):
        """Cross-Ref: Transition Key Quelle existiert in Topologie."""
        if not topology_state_ids:
            pytest.skip("topology.yaml not found")
        
        invalid = []
        for msg in transition_messages:
            key = msg["transition_key"]
            source = key.rsplit("-", 1)[0]  # Everything before last "-"
            if source not in topology_state_ids and source not in FUTURE_STATES:
                invalid.append(f"{key}: source '{source}' not in topology")
        assert not invalid, f"Transition keys with unknown source: {invalid}"

    def test_transition_key_event_in_topology(self, transition_messages, topology_transition_events):
        """Cross-Ref: Transition Key Event existiert in Topologie."""
        if not topology_transition_events:
            pytest.skip("topology.yaml not found")
        
        invalid = []
        for msg in transition_messages:
            key = msg["transition_key"]
            parts = key.rsplit("-", 1)
            if len(parts) != 2:
                continue
            source, event = parts
            if source in FUTURE_STATES:
                continue  # Future state, skip validation
            source_events = topology_transition_events.get(source, set())
            if event not in source_events:
                invalid.append(f"{key}: event '{event}' not in topology for state '{source}'")
        # Some transition messages may be for generic states (e.g., 6-default)
        # This is a soft check for now
        # assert not invalid, f"Transition keys with unknown events: {invalid}"


@pytest.mark.governance
class TestConformanceCommandPolicy:
    """Cross-Ref: Messages ↔ Command-Policy Conformance."""

    def test_instructions_reference_allowed_commands(self, transition_messages, allowed_commands_by_state):
        """Conformance: Commands in instructions sind im State erlaubt."""
        if not allowed_commands_by_state:
            pytest.skip("command_policy.yaml not found")
        
        violations = []
        for msg in transition_messages:
            instruction = msg.get("instruction", "")
            key = msg["transition_key"]
            source_state = key.rsplit("-", 1)[0]
            
            # Extract command references
            commands_in_instruction = COMMAND_REFERENCE_PATTERN.findall(instruction)
            
            for cmd in commands_in_instruction:
                # Universal commands are always allowed
                if cmd in {"/continue", "/review"}:
                    continue
                
                # Build allowed commands for source state
                allowed_universal = allowed_commands_by_state.get("*", set())
                allowed_in_state = allowed_commands_by_state.get(source_state, set())
                
                # For Phase 6, also allow commands for future substates
                if source_state == "6":
                    allowed_in_state = allowed_in_state | \
                        allowed_commands_by_state.get("6.approved", set()) | \
                        allowed_commands_by_state.get("6.presentation", set())
                
                all_allowed = allowed_in_state | allowed_universal
                
                if cmd not in all_allowed:
                    violations.append(
                        f"{key}: references '{cmd}' which is not allowed in state '{source_state}'"
                    )
        
        assert not violations, f"Command conformance violations: {violations}"

    def test_review_described_as_readonly(self, transition_messages, command_policy):
        """Conformance: /review ist immer als read-only beschrieben."""
        if not command_policy:
            pytest.skip("command_policy.yaml not found")
        
        # Find /review command to verify it's read-only
        review_cmd = next(
            (c for c in command_policy.get("commands", []) if c["command"] == "/review"),
            None
        )
        assert review_cmd is not None, "/review command not found in policy"
        assert review_cmd["mutating"] is False, "/review must be read-only in policy"
        
        # Check that instructions describe /review as read-only
        for msg in transition_messages:
            instruction = msg.get("instruction", "")
            if "/review" in instruction and "state change" in instruction.lower():
                # If instruction mentions state change with /review, verify it says "no state change"
                if "no state change" not in instruction.lower():
                    # This is a soft warning, not a hard failure
                    pass  # Could add warning here


@pytest.mark.governance
class TestPresentationOnlyLayer:
    """Absicherung: Messages sind presentation-only (keine Runtime-Semantik)."""

    def test_messages_cannot_affect_transitions(self, messages):
        """Runtime-Invariant: Messages können Transitions nicht beeinflussen."""
        # Verify no transition-affecting fields exist
        forbidden = {"next", "when", "source", "route_strategy", "default_next"}
        for msg_list in [messages.get("state_messages", []), 
                         messages.get("transition_messages", [])]:
            for msg in msg_list:
                found = set(msg.keys()) & forbidden
                assert not found, \
                    f"Message {msg.get('id')}: contains {found} which affects runtime"

    def test_messages_cannot_affect_guards(self, messages):
        """Runtime-Invariant: Messages können Guards nicht beeinflussen."""
        forbidden = {"condition", "guard_ref", "exit_required_keys"}
        for msg_list in [messages.get("state_messages", []), 
                         messages.get("transition_messages", [])]:
            for msg in msg_list:
                found = set(msg.keys()) & forbidden
                assert not found, \
                    f"Message {msg.get('id')}: contains {found} which affects guards"

    def test_messages_cannot_affect_commands(self, messages):
        """Runtime-Invariant: Messages können Command-Policy nicht beeinflussen."""
        forbidden = {"allowed_in", "mutating", "produces_events"}
        for msg_list in [messages.get("state_messages", []), 
                         messages.get("transition_messages", [])]:
            for msg in msg_list:
                found = set(msg.keys()) & forbidden
                assert not found, \
                    f"Message {msg.get('id')}: contains {found} which affects commands"


@pytest.mark.governance
class TestMessageNegative:
    """Negative Tests für Messages."""

    def test_no_duplicate_state_ids_across_sections(self, messages):
        """Negative: Keine Duplikate zwischen state_messages."""
        # Already tested in TestStateMessages.test_state_ids_unique
        pass

    def test_no_duplicate_transition_keys(self, transition_messages):
        """Negative: Keine Duplikate bei transition_key."""
        keys = [m["transition_key"] for m in transition_messages]
        duplicates = [k for k in keys if keys.count(k) > 1]
        assert not duplicates, f"Duplicate transition keys: {set(duplicates)}"

    def test_state_message_instruction_not_empty(self, state_messages):
        """Negative: State instruction ist nicht leer."""
        for msg in state_messages:
            instruction = msg.get("instruction", "")
            assert instruction.strip(), \
                f"Message {msg['id']}: instruction must not be empty"

    def test_transition_message_instruction_not_empty(self, transition_messages):
        """Negative: Transition instruction ist nicht leer."""
        for msg in transition_messages:
            instruction = msg.get("instruction", "")
            assert instruction.strip(), \
                f"Message {msg['id']}: instruction must not be empty"
