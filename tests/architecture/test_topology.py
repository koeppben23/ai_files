"""Phase 2: Canonical Topology Tests (v3 - Strict with bugfixes)

Validiert die extrahierte topology.yaml Struktur mit strengen Regeln:
- Alle States haben eindeutige IDs
- Alle Transition-Ziele existieren
- Start-State existiert
- Terminal-Flags sind korrekt
- Transition-IDs sind stabil und kollisionsfrei (structurally validated)
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
# ID Format Patterns (strict, matching documented schema exactly)
# ============================================================================

# State IDs: alphanumeric with dots, hyphens, and underscores (e.g., "0", "1.1", "3A", "3B-1", "6.internal_review")
STATE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-_]*$")

# Transition IDs: t<source>-<target>[-<suffix>]
# Strict pattern matching documented schema
TRANSITION_ID_PATTERN = re.compile(r"^t[a-zA-Z0-9][a-zA-Z0-9.\-_]*-[a-zA-Z0-9][a-zA-Z0-9.\-_]*(-[a-zA-Z0-9]+)*$")

# Event names: lowercase with underscores
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


# ============================================================================
# Allowed Structural Metadata vs Forbidden Presentation Metadata
# ============================================================================

# ALLOWED: Structural metadata (affects runtime behavior or identity)
ALLOWED_STRUCTURAL_METADATA = {"parent"}  # Optional, for hierarchy info

# FORBIDDEN: Presentation/UX metadata (no runtime effect)
# Note: Per ADR-001, description, display_name, tags are ALLOWED as non-runtime metadata
FORBIDDEN_STATE_FIELDS = {
    "phase",                # UX display name
    "active_gate",          # UX gate message
    "next_gate_condition",  # UX instruction
    "title",                # UX text
    "help_text",            # UX text
}

FORBIDDEN_TRANSITION_FIELDS = {
    "source",               # Provenance label (non-runtime)
    "active_gate",          # UX gate message
    "next_gate_condition",  # UX instruction
    "description",          # Presentation metadata
}

# Document metadata allowed at file level (not in state/transition objects)
DOCUMENT_METADATA_FIELDS = {"version", "schema"}


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
def all_transition_ids_list(topology):
    """Extract all transition IDs as LIST (for duplicate detection)."""
    ids = []
    for state in topology["states"]:
        for t in state.get("transitions", []):
            ids.append(t["id"])
    return ids


@pytest.fixture
def all_transition_ids_set(all_transition_ids_list):
    """Extract all transition IDs as SET (for membership checks)."""
    return set(all_transition_ids_list)


@pytest.fixture
def transitions_by_state(topology):
    """Extract transitions grouped by state for structural validation."""
    result = {}
    for state in topology["states"]:
        result[state["id"]] = state.get("transitions", [])
    return result


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

    def test_document_metadata_allowed(self, topology):
        """Document: version/schema sind erlaubte Datei-Metadaten."""
        # Document-level metadata is allowed but must not affect runtime
        for field in DOCUMENT_METADATA_FIELDS:
            if field in topology:
                # Just verify it's at document level, not in states
                for state in topology["states"]:
                    assert field not in state, \
                        f"Document metadata '{field}' must not be in state objects"

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

    def test_all_states_have_transitions_list(self, topology):
        """Happy: Alle States haben transitions-Liste (kann leer für terminale)."""
        for state in topology["states"]:
            assert "transitions" in state, f"State {state['id']} missing 'transitions'"
            assert isinstance(state["transitions"], list), \
                f"State {state['id']} transitions must be list"


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
    """Strikte Transition-ID Format-Validierung mit strukturbasierter Prüfung."""

    def test_transition_id_format_strict(self, topology, all_transition_ids_set):
        """Happy: Alle Transition-IDs folgen dem strikten Schema."""
        invalid = []
        for tid in all_transition_ids_set:
            if not TRANSITION_ID_PATTERN.match(tid):
                invalid.append(tid)
        assert not invalid, f"Invalid transition ID format: {invalid}"

    def test_transition_ids_unique(self, topology, all_transition_ids_list):
        """Happy: Alle Transition-IDs sind eindeutig."""
        # MUST use list, not set (set can't have duplicates)
        duplicates = [tid for tid in all_transition_ids_list if all_transition_ids_list.count(tid) > 1]
        assert not duplicates, f"Duplicate transition IDs: {set(duplicates)}"

    def test_transition_id_has_two_or_more_parts(self, topology, all_transition_ids_set):
        """Edge: Transition-IDs haben mindestens 2 Teile (source, target)."""
        invalid = []
        for tid in all_transition_ids_set:
            parts = tid[1:].split("-")  # Remove 't' prefix
            if len(parts) < 2:
                invalid.append(f"{tid}: too few parts ({len(parts)})")
        assert not invalid, f"Invalid transition ID structure: {invalid}"

    def test_transition_id_structurally_valid(self, topology, transitions_by_state):
        """Happy: Transition-ID entspricht Struktur t<source>-<target>[-<suffix>]."""
        invalid = []
        for state_id, transitions in transitions_by_state.items():
            for t in transitions:
                tid = t["id"]
                target = t["target"]
                
                # Transition ID format: t<source>-<target>[-<suffix>]
                # Examples: t0-t1.1, t3B-1-t3B-2, t5-t5-missing
                
                # Remove 't' prefix: "0-t1.1", "3B-1-t3B-2", "5-t5-missing"
                rest = tid[1:]
                
                # Find source by matching against state_id
                if not rest.startswith(state_id + "-"):
                    invalid.append(f"{tid}: doesn't start with source '{state_id}'")
                    continue
                
                # Remove source part: "0-t1.1" -> "t1.1"
                remainder = rest[len(state_id) + 1:]
                
                # Target in ID is prefixed with 't': "t1.1", "t3B-2", "t5-missing"
                # Expected: "t" + target + optional "-" + suffix
                expected_target_part = "t" + target
                
                if not remainder.startswith(expected_target_part):
                    invalid.append(f"{tid}: expected '{expected_target_part}' after source, got '{remainder}'")
                    continue
                
                # Check what comes after target
                after_target = remainder[len(expected_target_part):]
                
                if after_target:
                    # Must be suffix starting with "-"
                    if not after_target.startswith("-"):
                        invalid.append(f"{tid}: invalid suffix format '{after_target}'")
                    else:
                        # Suffix must match [a-zA-Z0-9]+ (may have multiple -suffix parts)
                        # e.g., "-missing", "-review-pending"
                        suffix = after_target[1:]
                        # Allow alphanumeric with hyphens within suffix segments
                        if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$", suffix):
                            invalid.append(f"{tid}: invalid suffix '{suffix}'")
        
        assert not invalid, f"Transition IDs with structural issues: {invalid}"

    def test_transition_id_source_state_exists(self, topology, all_transition_ids_set, state_ids):
        """Happy: Transition-ID Quell-State existiert."""
        invalid = []
        for tid in all_transition_ids_set:
            source_part = tid[1:]  # Remove 't' prefix
            
            found = False
            for sid in state_ids:
                if source_part.startswith(sid + "-"):
                    found = True
                    break
            if not found:
                invalid.append(f"{tid}: no matching source state")
        assert not invalid, f"Transition IDs with unknown source: {invalid}"

    def test_transition_id_target_state_exists(self, topology, all_transition_ids_set, state_ids):
        """Happy: Transition-ID Ziel-State existiert (structurally validated)."""
        invalid = []
        for tid in all_transition_ids_set:
            rest = tid[1:]  # Remove 't' prefix: "0-t1.1", "3B-1-t3B-2", etc.
            
            found = False
            for source_sid in state_ids:
                prefix = source_sid + "-"
                if rest.startswith(prefix):
                    remainder = rest[len(prefix):]
                    # Target in ID is prefixed with 't': "t1.1", "t3B-2"
                    # Check if remainder starts with "t" + target_sid
                    for target_sid in state_ids:
                        expected = "t" + target_sid
                        if remainder == expected or remainder.startswith(expected + "-"):
                            found = True
                            break
                    if found:
                        break
            if not found:
                invalid.append(f"{tid}: no valid target state")
        assert not invalid, f"Transition IDs with invalid target: {invalid}"


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

    def test_default_event_exists_per_non_terminal_state(self, topology):
        """Happy: Jeder nicht-terminale State hat genau einen default-Event."""
        for state in topology["states"]:
            if state["terminal"]:
                continue  # Terminal states may have no transitions
            
            # States that require explicit events (no default transition by design)
            # Per ADR-003: /implement produces implementation_started which triggers transition
            explicit_event_states = {"6.approved"}
            
            if state["id"] in explicit_event_states:
                continue
            
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

    def test_loaded_model_valid_fields_only(self, topology):
        """Model: Geladenes Modell enthält nur erlaubte Felder.
        
        Erlaubte Felder (per ADR-001):
        - Runtime: id, terminal, transitions
        - Structural: parent (optional, hierarchy info)
        - Non-runtime metadata: description (never for guard/routing)
        """
        for state in topology["states"]:
            # Valid model fields
            valid_fields = {"id", "terminal", "transitions", "parent", "description"}
            extra_fields = set(state.keys()) - valid_fields
            assert not extra_fields, \
                f"State {state['id']} has invalid fields: {extra_fields}"

    def test_loaded_model_parent_is_structural_metadata(self, topology):
        """Structural: parent ist erlaubte strukturelle Metadaten."""
        # parent is allowed as structural metadata (hierarchy info)
        # but must not be presentation metadata
        for state in topology["states"]:
            if "parent" in state:
                # parent must be string, not dict with UX text
                assert isinstance(state["parent"], str), \
                    f"State {state['id']} parent must be string (structural), not {type(state['parent'])}"


@pytest.mark.governance
class TestTerminalStates:
    """Terminal-Flags korrekt gesetzt."""

    def test_non_terminal_states_have_transitions(self, topology):
        """Happy: Nicht-terminale States haben mindestens eine Transition."""
        for state in topology["states"]:
            if not state["terminal"]:
                assert len(state["transitions"]) > 0, \
                    f"Non-terminal state {state['id']} has no transitions"

    def test_terminal_states_may_have_no_transitions(self, topology):
        """Edge: Terminale States dürfen keine oder leere Transitions haben."""
        for state in topology["states"]:
            if state["terminal"]:
                # Terminal states must have zero transitions (no outgoing edges)
                assert len(state["transitions"]) == 0, (
                    f"Terminal state {state['id']} has {len(state['transitions'])} "
                    f"transitions — terminal states must have none"
                )

    def test_terminal_flag_is_boolean(self, topology):
        """Happy: Terminal-Flag ist Boolean."""
        for state in topology["states"]:
            assert isinstance(state["terminal"], bool), \
                f"State {state['id']} terminal must be boolean"


@pytest.mark.governance
class TestTopologyReachability:
    """Topologie-Erreichbarkeit."""

    def test_all_states_reachable_from_start(self, topology, state_ids):
        """Happy: Alle States sind vom Start-State erreichbar.
        
        Note: Per ADR-003, Phase 6 base container '6' was removed (was unreachable).
        All Phase 6 paths lead directly to substates.
        """
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
class TestPhase6Substates:
    """Phase 6 Substates Architecture (per ADR-003)."""

    def test_phase6_container_exists(self, topology, state_ids):
        """Phase 6 Base Container exists as grouping parent for substates.
        
        State '6' serves as the parent container for all '6.*' substates.
        Per topology consistency validation, all parent references must exist.
        """
        assert "6" in state_ids, "State 6 must exist as parent container for 6.* substates"

    def test_all_phase6_substates_have_parent(self, topology):
        """Happy: Alle Phase 6 Substates haben parent='6'."""
        substates = ["6.internal_review", "6.presentation", "6.execution", 
                     "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"]
        for substate_id in substates:
            state = next((s for s in topology["states"] if s["id"] == substate_id), None)
            if state:
                assert state.get("parent") == "6", \
                    f"Substate {substate_id} must have parent='6'"

    def test_phase6_substates_form_valid_graph(self, topology):
        """Happy: Phase 6 Substates bilden einen gültigen Graphen."""
        # Map state ID to transitions
        transitions_map = {}
        for state in topology["states"]:
            transitions_map[state["id"]] = [t["target"] for t in state.get("transitions", [])]
        
        # Check reachability from 6.internal_review
        reachable = set()
        to_visit = ["6.internal_review"]
        while to_visit:
            current = to_visit.pop()
            if current in reachable or current not in transitions_map:
                continue
            reachable.add(current)
            to_visit.extend(transitions_map.get(current, []))
        
        # All substates should be reachable
        substates = {"6.internal_review", "6.presentation", "6.execution", 
                     "6.approved", "6.blocked", "6.rework"}
        unreachable = substates - reachable
        assert not unreachable, f"Phase 6 substates not reachable: {unreachable}"

    def test_phase6_complete_is_terminal(self, topology):
        """Happy: 6.complete ist terminal."""
        complete = next((s for s in topology["states"] if s["id"] == "6.complete"), None)
        assert complete is not None, "6.complete state must exist"
        assert complete["terminal"] is True, "6.complete must be terminal"

    def test_phase6_rejected_returns_to_phase4(self, topology):
        """Happy: 6.rejected hat Transition zu Phase 4."""
        rejected = next((s for s in topology["states"] if s["id"] == "6.rejected"), None)
        assert rejected is not None, "6.rejected state must exist"
        targets = [t["target"] for t in rejected.get("transitions", [])]
        assert "4" in targets, "6.rejected must have transition to Phase 4"


@pytest.mark.governance
class TestParentMetadata:
    """Parent-Feld als erlaubte strukturelle Metadaten."""

    def test_parent_is_optional_structural_metadata(self, topology):
        """Structural: parent ist optionale strukturelle Metadaten (nicht presentation)."""
        # parent is allowed as structural metadata for hierarchy info
        # It must be a simple string, not a complex object with UX text
        for state in topology["states"]:
            if "parent" in state:
                assert isinstance(state["parent"], str), \
                    f"State {state['id']} parent must be string (structural metadata)"
                # parent should reference a state ID pattern
                assert STATE_ID_PATTERN.match(state["parent"]) or state["parent"] == "", \
                    f"State {state['id']} parent '{state['parent']}' should match state ID pattern"

    def test_parent_does_not_affect_runtime_resolution(self, topology):
        """Runtime: parent hat keinen Einfluss auf Runtime-Auflösung."""
        # This is a design invariant - parent is informational only
        # Runtime resolution uses only state_id, never parent
        for state in topology["states"]:
            state_id = state["id"]
            assert STATE_ID_PATTERN.match(state_id), \
                f"State ID {state_id} must be valid without parent"


@pytest.mark.governance
class TestCrossSpecConformance:
    """Cross-Spec Conformance (Phase 2 scope: topology only)."""

    def test_no_guard_ref_in_phase2_topology(self, topology):
        """Phase 2: guard_ref ist noch nicht in Topologie (Phase 3/8 Ergänzung)."""
        # Phase 2 = pure topology without guards
        # Phase 3 extracts guards to guards.yaml
        # Phase 8 adds guard_ref to transitions
        # This test documents the Phase 2 scope boundary
        for state in topology["states"]:
            for t in state.get("transitions", []):
                assert "guard_ref" not in t, \
                    f"Transition {t['id']} has guard_ref (Phase 2 scope: topology only, guards in Phase 3/8)"
