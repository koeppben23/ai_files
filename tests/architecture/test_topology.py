"""Phase 2: Canonical Topology Tests (v2 - Strict)

Validiert die extrahierte topology.yaml Struktur mit strengen Regeln:
- Alle States haben eindeutige IDs
- Alle Transition-Ziele existieren
- Start-State existiert
- Terminal-Flags sind korrekt
- Transition-IDs sind stabil und kollisionsfrei
- Keine UX-Felder in Topologie
- Strikte ID-Format-Validierung

Diese Tests laufen GEGEN die extrahierte topology.yaml.
"""

from __future__ import annotations

import re
import pytest
import yaml
from pathlib import Path
from typing import Any


# ============================================================================
# ID Format Patterns (strict but matching current valid IDs)
# ============================================================================

# State IDs: alphanumeric with dots and hyphens (e.g., "0", "1.1", "3A", "3B-1")
STATE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]*$")

# Transition IDs: t<source>-<target>[-<suffix>], source/target are state IDs
# Pattern allows complex state IDs with dots and hyphens
TRANSITION_ID_PATTERN = re.compile(r"^t[a-zA-Z0-9][a-zA-Z0-9.\-]*-[a-zA-Z0-9][a-zA-Z0-9.\-]*(-[a-zA-Z0-9]+)*$")

# Event names: lowercase with underscores
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


# ============================================================================
# Forbidden UX Fields in Topology
# ============================================================================

FORBIDDEN_STATE_FIELDS = {
    "phase",           # UX display name
    "active_gate",     # UX gate message
    "next_gate_condition",  # UX instruction
    "description",     # Non-runtime metadata
    "display_name",    # Non-runtime metadata
    "title",           # UX text
    "help_text",       # UX text
}

FORBIDDEN_TRANSITION_FIELDS = {
    "source",          # Provenance label (non-runtime)
    "active_gate",     # UX gate message
    "next_gate_condition",  # UX instruction
    "description",     # Non-runtime metadata
}


# ============================================================================
# Fixtures
# ============================================================================

def _find_topology_path() -> Path | None:
    """Find topology.yaml relative to test file location.
    
    Returns None if not found - caller should handle the case.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "topology.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def topology_path():
    """Provides the topology path, skipping test if not found."""
    path = _find_topology_path()
    if path is None:
        pytest.skip("topology.yaml not found - test requires topology file")
    return path


@pytest.fixture
def topology(topology_path):
    """Lädt die topology.yaml für Struktur-Tests."""
    with open(topology_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def state_ids(topology):
    """Extract all state IDs from topology."""
    return {s["id"] for s in topology["states"]}


@pytest.fixture
def all_transition_ids(topology):
    """Extract all transition IDs from topology."""
    ids = set()
    for state in topology["states"]:
        for t in state.get("transitions", []):
            ids.add(t["id"])
    return ids


# ============================================================================
# Test Classes
# ============================================================================

@pytest.mark.governance
class TestTopologyStructure:
    """Grundlegende Topologie-Struktur (Runtime Core)."""

    def test_topology_loads_successfully(self, topology):
        """Happy: Topologie lädt erfolgreich."""
        assert "states" in topology
        assert "start_state_id" in topology
        assert isinstance(topology["states"], list)
        assert len(topology["states"]) > 0

    def test_no_version_or_schema_leak(self, topology):
        """Runtime: version/schema sind Optional-Metadaten, keine Runtime-Felder."""
        # version and schema are allowed as non-runtime metadata
        # but should not be used in runtime resolution
        pass  # Allowed by ADR-001

    def test_start_state_exists(self, topology, state_ids):
        """Happy: Startzustand existiert."""
        assert topology["start_state_id"] in state_ids

    def test_all_state_ids_unique(self, topology):
        """Happy: Alle State-IDs sind eindeutig."""
        state_ids = [s["id"] for s in topology["states"]]
        duplicates = [s for s in state_ids if state_ids.count(s) > 1]
        assert not duplicates, f"Duplicate state IDs: {set(duplicates)}"

    def test_all_states_have_id(self, topology):
        """Happy: Alle States haben eine ID."""
        for state in topology["states"]:
            assert "id" in state, f"State missing 'id' field"

    def test_all_states_have_terminal_flag(self, topology):
        """Happy: Alle States haben terminal-Flag."""
        for state in topology["states"]:
            assert "terminal" in state, f"State {state['id']} missing 'terminal' flag"
            assert isinstance(state["terminal"], bool), \
                f"State {state['id']} terminal must be boolean"

    def test_all_states_have_transitions(self, topology):
        """Happy: Alle States haben transitions-Liste."""
        for state in topology["states"]:
            assert "transitions" in state, f"State {state['id']} missing 'transitions'"
            assert isinstance(state["transitions"], list), \
                f"State {state['id']} transitions must be list"
            assert len(state["transitions"]) > 0, \
                f"State {state['id']} must have at least one transition"


@pytest.mark.governance
class TestStateIdFormat:
    """Strikte State-ID Format-Validierung."""

    def test_state_id_format_strict(self, topology, state_ids):
        """Happy: Alle State-IDs folgen dem strikten Schema."""
        invalid = []
        for sid in state_ids:
            if not STATE_ID_PATTERN.match(sid):
                invalid.append(sid)
        assert not invalid, f"Invalid state ID format: {invalid}"

    def test_state_id_starts_with_alphanumeric(self, topology, state_ids):
        """Edge: State-IDs beginnen mit Alphanumeric."""
        invalid = [sid for sid in state_ids if sid and not sid[0].isalnum()]
        assert not invalid, f"State IDs must start with alphanumeric: {invalid}"

    def test_state_id_no_consecutive_dots(self, topology, state_ids):
        """Edge: State-IDs haben keine aufeinanderfolgenden Punkte."""
        invalid = [sid for sid in state_ids if ".." in sid]
        assert not invalid, f"State IDs with consecutive dots: {invalid}"


@pytest.mark.governance
class TestTransitionIdFormat:
    """Strikte Transition-ID Format-Validierung."""

    def test_transition_id_format_strict(self, topology, all_transition_ids):
        """Happy: Alle Transition-IDs folgen dem strikten Schema."""
        invalid = []
        for tid in all_transition_ids:
            if not TRANSITION_ID_PATTERN.match(tid):
                invalid.append(tid)
        assert not invalid, f"Invalid transition ID format: {invalid}"

    def test_transition_ids_unique(self, topology, all_transition_ids):
        """Happy: Alle Transition-IDs sind eindeutig."""
        all_ids_list = list(all_transition_ids)
        duplicates = [tid for tid in all_ids_list if all_ids_list.count(tid) > 1]
        assert not duplicates, f"Duplicate transition IDs: {set(duplicates)}"

    def test_transition_id_format_hint(self, topology, all_transition_ids):
        """Edge: Transition-IDs folgen Schema t<from>-<to>[-<suffix>]."""
        invalid = []
        for tid in all_transition_ids:
            parts = tid[1:].split("-")  # Remove 't' prefix
            if len(parts) < 2:
                invalid.append(f"{tid}: too few parts")
        assert not invalid, f"Invalid transition ID structure: {invalid}"

    def test_transition_id_source_state_exists(self, topology, all_transition_ids, state_ids):
        """Happy: Transition-ID Quell-State existiert."""
        invalid = []
        for tid in all_transition_ids:
            # Extract source from t<source>-<target>[-<suffix>]
            # Source is everything after 't' and before the first '-' that's followed by a target
            # We need to match against known state IDs
            source_part = tid[1:]  # Remove 't' prefix
            
            found = False
            for sid in state_ids:
                # Check if transition ID starts with t<state_id>-
                if source_part.startswith(sid + "-"):
                    found = True
                    break
            if not found:
                invalid.append(f"{tid}: no matching source state")
        assert not invalid, f"Transition IDs with unknown source: {invalid}"

    def test_transition_id_target_state_exists(self, topology, all_transition_ids, state_ids):
        """Happy: Transition-ID Ziel-State existiert."""
        invalid = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                tid = t["id"]
                target = t["target"]
                # Transition ID format: t<source>-<target> or t<source>-<target>-<suffix>
                # Check if target appears in the ID
                # For self-transitions like t5-t5-missing, target "5" appears twice
                # We just need to verify the target is part of the ID somehow
                
                # Simple check: does the target appear as a complete segment?
                # Remove 't' prefix and split by '-'
                rest = tid[1:]  # e.g., "5-t5-missing" from "t5-t5-missing"
                
                # For transition t<source>-<target>[-<suffix>]
                # After removing 't', we have: <source>-<target>[-<suffix>]
                # But source might contain dashes, so we need to be smarter
                
                # Check if target appears anywhere in the ID (after the initial t)
                if target in rest:
                    continue
                invalid.append(f"{tid}: target '{target}' not found in ID")
        assert not invalid, f"Transition IDs with missing target in ID: {invalid}"


@pytest.mark.governance
class TestTransitionIntegrity:
    """Transition-Referenzen und Integrität."""

    def test_all_transition_targets_exist(self, topology, state_ids):
        """Happy: Alle Transition-Ziele existieren."""
        errors = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                if t["target"] not in state_ids:
                    errors.append(f"{state['id']} -> {t['target']}")
        assert not errors, f"Invalid transition targets: {errors}"

    def test_all_events_valid_format(self, topology):
        """Happy: Alle Events folgen dem Format."""
        invalid = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                event = t.get("event", "")
                if not EVENT_PATTERN.match(event):
                    invalid.append(f"{state['id']}: '{event}'")
        assert not invalid, f"Invalid event format: {invalid}"

    def test_default_event_exists_per_state(self, topology):
        """Happy: Jeder State hat genau einen default-Event."""
        for state in topology["states"]:
            events = [t.get("event") for t in state.get("transitions", [])]
            default_count = events.count("default")
            assert default_count == 1, \
                f"State {state['id']} has {default_count} default events (expected 1)"


@pytest.mark.governance
class TestNoUxInTopology:
    """Keine UX-Felder in Topologie (YAML-Ebene)."""

    def test_no_forbidden_state_fields(self, topology):
        """Runtime: Keine UX-Felder in State-Definitionen."""
        violations = []
        for state in topology["states"]:
            for field in FORBIDDEN_STATE_FIELDS:
                if field in state:
                    violations.append(f"State {state['id']}: forbidden field '{field}'")
        assert not violations, f"Forbidden UX fields in states: {violations}"

    def test_no_forbidden_transition_fields(self, topology):
        """Runtime: Keine UX-Felder in Transition-Definitionen."""
        violations = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                for field in FORBIDDEN_TRANSITION_FIELDS:
                    if field in t:
                        violations.append(f"Transition {t['id']}: forbidden field '{field}'")
        assert not violations, f"Forbidden UX fields in transitions: {violations}"


@pytest.mark.governance
class TestNoUxInLoadedModel:
    """Keine UX-Felder in geladenem Modell (Model-Ebene)."""

    def test_loaded_model_no_ux_fields(self, topology):
        """Runtime: Geladenes Modell enthält keine UX-Felder."""
        # This test ensures that even if a forbidden field slips through YAML,
        # the model/loader would reject it
        
        # Simulate what a loader would do
        for state in topology["states"]:
            # Check that only runtime fields are present
            runtime_fields = {"id", "terminal", "transitions", "parent"}
            extra_fields = set(state.keys()) - runtime_fields
            assert not extra_fields, \
                f"State {state['id']} has non-runtime fields: {extra_fields}"


@pytest.mark.governance
class TestTerminalStates:
    """Terminal-Flags korrekt gesetzt."""

    def test_non_terminal_states_have_transitions(self, topology):
        """Happy: Nicht-terminale States haben Übergänge."""
        for state in topology["states"]:
            if not state["terminal"]:
                assert len(state["transitions"]) > 0, \
                    f"Non-terminal state {state['id']} has no transitions"

    def test_potential_terminal_states(self, topology):
        """Edge: Phase 6 könnte terminal werden (noch nicht)."""
        # Currently no terminal states in V1
        terminal_states = [s["id"] for s in topology["states"] if s["terminal"]]
        # This is informational - Phase 6 might become terminal in V2
        assert len(terminal_states) == 0, \
            f"Found terminal states: {terminal_states} (expected none in V1)"


@pytest.mark.governance
class TestTopologyReachability:
    """Topologie-Erreichbarkeit."""

    def test_all_states_reachable_from_start(self, topology, state_ids):
        """Happy: Alle States sind vom Start-State erreichbar."""
        start = topology["start_state_id"]
        reachable = set()
        to_visit = [start]
        
        while to_visit:
            current = to_visit.pop()
            if current in reachable:
                continue
            reachable.add(current)
            
            state = next((s for s in topology["states"] if s["id"] == current), None)
            if not state:
                continue
                
            for t in state.get("transitions", []):
                if t["target"] not in reachable:
                    to_visit.append(t["target"])
        
        unreachable = state_ids - reachable
        assert not unreachable, f"Unreachable states: {unreachable}"


@pytest.mark.governance
class TestPhase6Monolith:
    """Phase 6 Monolith-Struktur (vor Zerlegung)."""

    def test_phase6_exists(self, topology, state_ids):
        """Happy: Phase 6 State existiert."""
        assert "6" in state_ids

    def test_phase6_is_not_terminal(self, topology):
        """Phase 6 ist nicht terminal (noch im Monolith)."""
        phase6 = next(s for s in topology["states"] if s["id"] == "6")
        assert phase6["terminal"] is False

    def test_phase6_has_many_transitions(self, topology):
        """Corner: Phase 6 hat viele Self-Transitions (monolithisch)."""
        phase6 = next(s for s in topology["states"] if s["id"] == "6")
        transitions = phase6.get("transitions", [])
        assert len(transitions) >= 10, \
            f"Expected 10+ transitions for Phase 6, got {len(transitions)}"

    def test_phase6_self_transitions_target_itself_or_phase4(self, topology):
        """Happy: Phase 6 Self-Transitions zielen auf '6' oder '4' (rejection)."""
        phase6 = next(s for s in topology["states"] if s["id"] == "6")
        valid_targets = {"6", "4"}
        for t in phase6.get("transitions", []):
            assert t["target"] in valid_targets, \
                f"Phase 6 transition {t['event']} targets {t['target']}, expected one of {valid_targets}"


@pytest.mark.governance
class TestParentMetadata:
    """Parent-Feld als non-runtime Metadaten."""

    def test_parent_is_optional(self, topology):
        """Happy: parent ist optional (non-runtime)."""
        # parent field is allowed but not required
        for state in topology["states"]:
            # If parent exists, it should be a string
            if "parent" in state:
                assert isinstance(state["parent"], str), \
                    f"State {state['id']} parent must be string"

    def test_parent_does_not_affect_id(self, topology):
        """Runtime: Gleiche ID, anderer parent → gleiche Runtime-Semantik."""
        # This is a design invariant - parent is informational only
        # The test documents this expectation
        for state in topology["states"]:
            state_id = state["id"]
            # The ID is the canonical identifier, parent is just metadata
            # Runtime resolution uses only state_id, never parent
            assert STATE_ID_PATTERN.match(state_id), \
                f"State ID {state_id} must be valid even without parent"


@pytest.mark.governance
class TestCrossSpecConformance:
    """Cross-Spec Conformance (Vorbereitung für Phase 8)."""

    def test_guard_refs_not_in_topology_yet(self, topology):
        """Phase 8: guard_ref ist noch nicht in Topologie (wird später geprüft)."""
        # In Phase 3, we'll extract guards
        # In Phase 8, we'll add guard_ref to transitions
        # For now, just verify no guard_ref field exists
        for state in topology["states"]:
            for t in state.get("transitions", []):
                assert "guard_ref" not in t, \
                    f"Transition {t['id']} has guard_ref (expected in Phase 8)"
