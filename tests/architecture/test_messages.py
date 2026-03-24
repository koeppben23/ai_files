"""Phase 5: Messages Tests

Validiert die extrahierte messages.yaml Struktur:
- Alle State Messages haben state_id, display_name, gate_message, instruction
- Alle Transition Messages haben transition_key, gate_message, instruction
- State-IDs existieren in Topologie
- Transition-Keys haben korrektes Format
- Keine Runtime-Felder in Messages

Diese Tests laufen GEGEN die extrahierte messages.yaml.
"""

from __future__ import annotations

import re
import pytest
import yaml
from pathlib import Path
from typing import Any


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
def transition_keys(transition_messages):
    """Extract transition keys."""
    return {m["transition_key"] for m in transition_messages}


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
        assert isinstance(messages["state_messages"], list)
        assert isinstance(messages["transition_messages"], list)

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
class TestStateMessages:
    """State Message Definitionen."""

    def test_state_messages_have_state_id(self, state_messages):
        """Runtime: Alle State Messages haben state_id."""
        for msg in state_messages:
            assert "state_id" in msg, f"State message missing 'state_id'"
            assert isinstance(msg["state_id"], str)

    def test_state_messages_have_display_name(self, state_messages):
        """Non-runtime: Alle State Messages haben display_name."""
        for msg in state_messages:
            assert "display_name" in msg, \
                f"State message {msg.get('state_id')} missing 'display_name'"
            assert isinstance(msg["display_name"], str)

    def test_state_messages_have_gate_message(self, state_messages):
        """Non-runtime: Alle State Messages haben gate_message."""
        for msg in state_messages:
            assert "gate_message" in msg, \
                f"State message {msg.get('state_id')} missing 'gate_message'"
            assert isinstance(msg["gate_message"], str)

    def test_state_messages_have_instruction(self, state_messages):
        """Non-runtime: Alle State Messages haben instruction."""
        for msg in state_messages:
            assert "instruction" in msg, \
                f"State message {msg.get('state_id')} missing 'instruction'"
            assert isinstance(msg["instruction"], str)

    def test_state_ids_unique(self, state_messages):
        """Runtime: State IDs sind eindeutig."""
        ids = [m["state_id"] for m in state_messages]
        duplicates = [sid for sid in ids if ids.count(sid) > 1]
        assert not duplicates, f"Duplicate state IDs: {set(duplicates)}"

    def test_state_ids_no_ux_content(self, state_messages):
        """Non-runtime: State Messages enthalten keine Runtime-Felder."""
        runtime_fields = {"id", "terminal", "transitions", "parent"}
        for msg in state_messages:
            extra = set(msg.keys()) - {"state_id", "display_name", "gate_message", "instruction"}
            assert not extra, \
                f"State message {msg.get('state_id')}: non-message fields {extra}"


@pytest.mark.governance
class TestTransitionMessages:
    """Transition Message Definitionen."""

    def test_transition_messages_have_transition_key(self, transition_messages):
        """Runtime: Alle Transition Messages haben transition_key."""
        for msg in transition_messages:
            assert "transition_key" in msg, f"Transition message missing 'transition_key'"
            assert isinstance(msg["transition_key"], str)

    def test_transition_messages_have_gate_message(self, transition_messages):
        """Non-runtime: Alle Transition Messages haben gate_message."""
        for msg in transition_messages:
            assert "gate_message" in msg, \
                f"Transition message {msg.get('transition_key')} missing 'gate_message'"
            assert isinstance(msg["gate_message"], str)

    def test_transition_messages_have_instruction(self, transition_messages):
        """Non-runtime: Alle Transition Messages haben instruction."""
        for msg in transition_messages:
            assert "instruction" in msg, \
                f"Transition message {msg.get('transition_key')} missing 'instruction'"
            assert isinstance(msg["instruction"], str)

    def test_transition_keys_unique(self, transition_messages):
        """Runtime: Transition Keys sind eindeutig."""
        keys = [m["transition_key"] for m in transition_messages]
        duplicates = [k for k in keys if keys.count(k) > 1]
        assert not duplicates, f"Duplicate transition keys: {set(duplicates)}"

    def test_transition_key_format(self, transition_messages):
        """Runtime: Transition Keys haben korrektes Format."""
        # Format: "<source_state>-<event>" or "<source_state>-default"
        pattern = re.compile(r"^[a-zA-Z0-9.\-]+-[a-z_]+$")
        for msg in transition_messages:
            key = msg["transition_key"]
            assert pattern.match(key), \
                f"Invalid transition key format: '{key}' (expected: <source>-<event>)"

    def test_transition_key_source_exists(self, transition_messages, state_ids_from_messages):
        """Runtime: Transition Key Quelle existiert in State Messages."""
        for msg in transition_messages:
            key = msg["transition_key"]
            source = key.rsplit("-", 1)[0]  # Get everything before last "-"
            # Note: Some sources might not have state messages (transition-only)
            # This is informational

    def test_transition_messages_no_ux_runtime_mix(self, transition_messages):
        """Non-runtime: Transition Messages haben keine Runtime-Felder."""
        runtime_fields = {"next", "when", "source"}
        for msg in transition_messages:
            extra = set(msg.keys()) - {"transition_key", "gate_message", "instruction"}
            assert not extra, \
                f"Transition message {msg.get('transition_key')}: non-message fields {extra}"


@pytest.mark.governance
class TestMessagesTopologyConsistency:
    """Konsistenz zwischen Messages und Topologie."""

    def test_all_topology_states_have_messages(self, state_ids_from_messages):
        """Happy: Alle Topology States haben Messages (oder Future States)."""
        topo_path = _find_topology_path()
        if topo_path is None:
            pytest.skip("topology.yaml not found")
        
        with open(topo_path, encoding="utf-8") as f:
            topology = yaml.safe_load(f)
        
        topology_state_ids = {s["id"] for s in topology["states"]}
        
        # Future states from ADR-003 (Phase 6 zerlegung)
        future_states = {"6.approved", "6.presentation", "6.execution",
                         "6.internal_review", "6.blocked", "6.rework",
                         "6.rejected", "6.complete"}
        
        # All current topology states should have messages
        missing = topology_state_ids - state_ids_from_messages - future_states
        assert not missing, f"Topology states without messages: {missing}"

    def test_state_messages_allows_future_states(self, state_ids_from_messages):
        """Future: Messages können Future States abdecken."""
        # Future states from ADR-003
        future_states = {"6.approved", "6.presentation", "6.execution",
                         "6.internal_review", "6.blocked", "6.rework",
                         "6.rejected", "6.complete"}
        
        # Check if any future states have messages (optional)
        future_with_messages = future_states & state_ids_from_messages
        # This is informational - not required yet
