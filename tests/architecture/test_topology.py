"""Phase 2: Canonical Topology Tests

Validiert die extrahierte topology.yaml Struktur:
- Alle States haben eindeutige IDs
- Alle Transition-Ziele existieren
- Start-State existiert
- Route-Strategien sind gültig
- Topologie ist transitiv erreichbar

Diese Tests laufen GEGEN die extrahierte topology.yaml.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path


def _find_topology_path() -> Path | None:
    """Find topology.yaml relative to test file location.
    
    Returns None if not found - caller should handle the case.
    """
    current = Path(__file__).resolve()
    # Search upward from test file location
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


@pytest.mark.governance
class TestTopologyStructure:
    """Grundlegende Topologie-Struktur."""

    def test_topology_loads_successfully(self, topology):
        """Happy: Topologie lädt erfolgreich."""
        assert "states" in topology
        assert "start_state" in topology
        assert isinstance(topology["states"], list)
        assert len(topology["states"]) > 0

    def test_start_state_exists(self, topology):
        """Happy: Startzustand existiert."""
        state_ids = {s["id"] for s in topology["states"]}
        assert topology["start_state"] in state_ids

    def test_all_state_ids_unique(self, topology):
        """Happy: Alle State-IDs sind eindeutig."""
        state_ids = [s["id"] for s in topology["states"]]
        assert len(state_ids) == len(set(state_ids)), \
            f"Duplicate state IDs: {[s for s in state_ids if state_ids.count(s) > 1]}"


@pytest.mark.governance
class TestTransitionIntegrity:
    """Transition-Referenzen."""

    def test_all_transition_targets_exist(self, topology):
        """Happy: Alle Transition-Ziele existieren."""
        state_ids = {s["id"] for s in topology["states"]}
        errors = []
        for state in topology["states"]:
            for t in state.get("transitions", []):
                if t["next"] not in state_ids:
                    errors.append(f"{state['id']} -> {t['next']}")
        assert not errors, f"Invalid transition targets: {errors}"

    def test_all_default_next_exist(self, topology):
        """Happy: Alle default_next Targets existieren."""
        state_ids = {s["id"] for s in topology["states"]}
        errors = []
        for state in topology["states"]:
            if "default_next" in state and state["default_next"] not in state_ids:
                errors.append(f"{state['id']} default_next -> {state['default_next']}")
        assert not errors, f"Invalid default_next targets: {errors}"


@pytest.mark.governance
class TestRouteStrategy:
    """Route-Strategien."""

    def test_all_route_strategies_valid(self, topology):
        """Happy: Alle route_strategy Werte sind gültig."""
        valid_strategies = {"stay", "next"}
        for state in topology["states"]:
            strategy = state.get("route_strategy")
            assert strategy in valid_strategies, \
                f"State {state['id']} has invalid route_strategy: {strategy}"

    def test_stay_states_have_transitions(self, topology):
        """Edge: States mit route_strategy 'stay' haben transitions."""
        for state in topology["states"]:
            if state.get("route_strategy") == "stay":
                has_transitions = len(state.get("transitions", [])) > 0
                has_default = "default_next" in state
                assert has_transitions or has_default, \
                    f"State {state['id']} with route_strategy 'stay' has no transitions or default_next"


@pytest.mark.governance
class TestTopologyReachability:
    """Topologie-Erreichbarkeit."""

    def test_all_states_reachable_from_start(self, topology):
        """Happy: Alle States sind vom Start-State erreichbar."""
        start = topology["start_state"]
        reachable = set()
        to_visit = [start]
        
        while to_visit:
            current = to_visit.pop()
            if current in reachable:
                continue
            reachable.add(current)
            
            # Find the state definition
            state = next((s for s in topology["states"] if s["id"] == current), None)
            if not state:
                continue
                
            # Add default_next to queue
            if "default_next" in state:
                to_visit.append(state["default_next"])
            
            # Add transition targets to queue
            for t in state.get("transitions", []):
                to_visit.append(t["next"])
        
        all_state_ids = {s["id"] for s in topology["states"]}
        unreachable = all_state_ids - reachable
        assert not unreachable, f"Unreachable states: {unreachable}"


@pytest.mark.governance
class TestPhase6Monolith:
    """Phase 6 Monolith-Struktur (vor Zerlegung)."""

    def test_phase6_exists(self, topology):
        """Happy: Phase 6 State existiert."""
        state_ids = {s["id"] for s in topology["states"]}
        assert "6" in state_ids

    def test_phase6_is_stay(self, topology):
        """Phase 6 hat route_strategy 'stay'."""
        phase6 = next(s for s in topology["states"] if s["id"] == "6")
        assert phase6.get("route_strategy") == "stay"

    def test_phase6_has_many_transitions(self, topology):
        """Corner: Phase 6 hat viele Self-Transitions (monolithisch)."""
        phase6 = next(s for s in topology["states"] if s["id"] == "6")
        transitions = phase6.get("transitions", [])
        assert len(transitions) >= 10, \
            f"Expected 10+ transitions for Phase 6, got {len(transitions)}"

    def test_phase6_self_transitions_target_itself_or_phase4(self, topology):
        """Happy: Phase 6 Self-Transitions zielen auf '6' oder '4' (rejection)."""
        phase6 = next(s for s in topology["states"] if s["id"] == "6")
        valid_targets = {"6", "4"}  # 4 = rejection path to Phase 4
        for t in phase6.get("transitions", []):
            assert t["next"] in valid_targets, \
                f"Phase 6 transition {t.get('when')} targets {t['next']}, expected one of {valid_targets}"
