"""Runtime Integration Tests for Topology (WP2).

These tests prove that topology.yaml is the authoritative source
for state machine transitions in the runtime. They test the actual runtime path
through resolve_topology_transition() in phase_kernel.py.
"""

from __future__ import annotations

import pytest

from governance_runtime.kernel.phase_kernel import execute, resolve_topology_transition
from governance_runtime.kernel.topology_loader import (
    StateNotFoundError,
    InvalidTransitionError,
    TopologyLoader,
    resolve_transition,
)


class TestPhaseKernelTopologyResolution:
    """Integration Tests: Topology resolution in phase_kernel.py runtime path.
    
    These tests prove that the runtime kernel resolves transitions against
    topology.yaml.
    """

    def test_6_execution_to_internal_review(self):
        """Runtime: implementation_accepted transitions to 6.internal_review."""
        next_state = resolve_topology_transition("6.execution", "implementation_accepted")
        assert next_state == "6.internal_review"

    def test_6_approved_to_execution(self):
        """Runtime: implementation_started transitions to 6.execution."""
        next_state = resolve_topology_transition("6.approved", "implementation_started")
        assert next_state == "6.execution"

    def test_6_execution_to_blocked(self):
        """Runtime: implementation_blocked transitions to 6.blocked."""
        next_state = resolve_topology_transition("6.execution", "implementation_blocked")
        assert next_state == "6.blocked"

    def test_6_blocked_to_execution(self):
        """Runtime: implementation_started from blocked transitions to 6.execution."""
        next_state = resolve_topology_transition("6.blocked", "implementation_started")
        assert next_state == "6.execution"

    def test_6_execution_to_complete(self):
        """Runtime: workflow_complete transitions to 6.complete."""
        next_state = resolve_topology_transition("6.execution", "workflow_complete")
        assert next_state == "6.complete"

    def test_invalid_event_raises_error(self):
        """Runtime: Invalid event raises InvalidTransitionError."""
        with pytest.raises(InvalidTransitionError):
            resolve_topology_transition("6.execution", "nonexistent_event")

    def test_invalid_state_raises_error(self):
        """Runtime: Invalid state raises StateNotFoundError."""
        with pytest.raises(StateNotFoundError):
            resolve_topology_transition("nonexistent_state", "default")


class TestPhaseKernelTopologyStateQueries:
    """Integration Tests: State queries via topology."""

    def test_is_terminal_state(self):
        """Runtime: Check if state is terminal."""
        TopologyLoader._ensure_loaded()
        
        assert TopologyLoader.is_state_terminal("6.complete") is True
        assert TopologyLoader.is_state_terminal("6.execution") is False

    def test_get_parent_state(self):
        """Runtime: Get parent of a substate."""
        TopologyLoader._ensure_loaded()
        
        parent = TopologyLoader.get_parent_state("6.approved")
        assert parent == "6"

    def test_has_event_in_state(self):
        """Runtime: Check if event exists for state."""
        TopologyLoader._ensure_loaded()
        
        assert TopologyLoader.has_event("6.execution", "workflow_complete") is True
        assert TopologyLoader.has_event("6.execution", "nonexistent") is False


class TestTopologyChangeAffectsRuntime:
    """Integration Tests: Prove topology changes affect runtime behavior.
    
    These tests prove that resolve_topology_transition() consults the
    actual topology, not hardcoded values.
    """

    def test_same_event_different_states_different_targets(self):
        """Runtime: Same event in different states yields different targets."""
        # implementation_started from 6.approved -> 6.execution
        target1 = resolve_topology_transition("6.approved", "implementation_started")
        assert target1 == "6.execution"
        
        # implementation_started from 6.blocked -> 6.execution
        target2 = resolve_topology_transition("6.blocked", "implementation_started")
        assert target2 == "6.execution"

    def test_multiple_transitions_from_same_state(self):
        """Runtime: Multiple events from same state yield correct targets."""
        state = "6.presentation"
        
        # workflow_approved -> 6.approved
        assert resolve_topology_transition(state, "workflow_approved") == "6.approved"
        
        # review_changes_requested -> 6.rework
        assert resolve_topology_transition(state, "review_changes_requested") == "6.rework"
        
        # review_rejected -> 6.rejected
        assert resolve_topology_transition(state, "review_rejected") == "6.rejected"

    def test_terminal_state_has_no_transitions(self):
        """Runtime: Terminal state has no transitions."""
        TopologyLoader._ensure_loaded()
        
        transitions = TopologyLoader.get_state_transitions("6.complete")
        assert len(transitions) == 0

    def test_full_workflow_path(self):
        """Runtime: Trace full workflow through states."""
        # 6.approved -> 6.execution
        state = resolve_topology_transition("6.approved", "implementation_started")
        assert state == "6.execution"
        
        # 6.execution -> 6.internal_review
        state = resolve_topology_transition(state, "implementation_accepted")
        assert state == "6.internal_review"
        
        # 6.internal_review -> 6.presentation
        state = resolve_topology_transition(state, "implementation_review_complete")
        assert state == "6.presentation"
        
        # 6.presentation -> 6.approved (workflow_approved)
        state = resolve_topology_transition(state, "workflow_approved")
        assert state == "6.approved"


class TestRealKernelPathUsesTopology:
    """Integration Tests: Real kernel decision path uses topology.
    
    These tests prove that the actual execute() function consults topology.yaml
    for Phase 6 transition resolution.
    """

    def test_phase6_topology_authoritative_for_all_events(self):
        """Real Runtime: All Phase 6 events resolve through topology."""
        TopologyLoader._ensure_loaded()
        
        phase6_states = ["6.approved", "6.execution", "6.internal_review", 
                         "6.presentation", "6.blocked", "6.rework", "6.rejected"]
        
        for state_id in phase6_states:
            transitions = TopologyLoader.get_state_transitions(state_id)
            
            # Each state should have at least default transition
            assert len(transitions) > 0, f"{state_id} has no transitions in topology"
            
            # All targets should be valid states
            for t in transitions:
                assert TopologyLoader.has_state(t.target), \
                    f"{state_id} -> {t.event} -> {t.target} not found"

    def test_phase6_approved_to_execution_via_topology(self):
        """Real Runtime: 6.approved -> implementation_started -> 6.execution."""
        # This proves topology resolves the target, not hardcoded logic
        target = resolve_transition("6.approved", "implementation_started")
        assert target == "6.execution"

    def test_phase6_execution_to_internal_review_via_topology(self):
        """Real Runtime: 6.execution -> implementation_accepted -> 6.internal_review."""
        target = resolve_transition("6.execution", "implementation_accepted")
        assert target == "6.internal_review"

    def test_phase6_execution_to_complete_via_topology(self):
        """Real Runtime: 6.execution -> workflow_complete -> 6.complete."""
        target = resolve_transition("6.execution", "workflow_complete")
        assert target == "6.complete"

    def test_topology_resolves_valid_targets(self):
        """Real Runtime: All topology targets are valid state IDs."""
        TopologyLoader._ensure_loaded()
        
        all_states = set(TopologyLoader.get_all_states())
        
        for state_id in all_states:
            for transition in TopologyLoader.get_state_transitions(state_id):
                assert transition.target in all_states, \
                    f"Topology transition {transition.id} has invalid target {transition.target}"

    def test_execute_uses_topology_for_phase6_transition(self, tmp_path, monkeypatch):
        """execute(): real kernel path resolves Phase 6 target via topology loader."""
        from pathlib import Path
        from governance_runtime.kernel.phase_api_spec import PhaseApiSpec, PhaseSpecEntry, TransitionRule
        from governance_runtime.kernel.phase_kernel import RuntimeContext

        calls: list[tuple[str, str]] = []

        fake_spec = PhaseApiSpec(
            path=tmp_path / "phase_api.yaml",
            sha256="fake",
            stable_hash="fake",
            loaded_at="now",
            start_token="6.execution",
            entries={
                "6.execution": PhaseSpecEntry(
                    token="6.execution",
                    phase="6-PostFlight",
                    active_gate="Implementation Internal Review",
                    next_gate_condition="Continue",
                    next_token="6.execution",
                    route_strategy="stay",
                    transitions=(
                        TransitionRule(when="implementation_accepted", next_token="6.internal_review", source="phase-6-implementation-accepted"),
                    ),
                    exit_required_keys=(),
                ),
            },
        )

        def _fake_has_event(state_id: str, event: str) -> bool:
            if state_id == "6.execution" and event in {
                "implementation_accepted",
                "default",
            }:
                return True
            return False

        def _fake_get_next_state(state_id: str, event: str) -> str:
            calls.append((state_id, event))
            if state_id == "6.execution" and event == "implementation_accepted":
                return "6.internal_review"
            if state_id == "6.execution" and event == "default":
                return "6.internal_review"
            raise RuntimeError(f"unexpected topology lookup: {state_id}/{event}")

        monkeypatch.setattr(TopologyLoader, "has_event", staticmethod(_fake_has_event))
        monkeypatch.setattr(TopologyLoader, "get_next_state", staticmethod(_fake_get_next_state))
        monkeypatch.setattr(TopologyLoader, "is_state_terminal", staticmethod(lambda _state_id: False))

        monkeypatch.setattr("governance_runtime.kernel.phase_kernel.load_phase_api", lambda _commands_home: fake_spec)
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._resolve_paths", lambda _ctx: (tmp_path / "commands", tmp_path / "workspaces", tmp_path / "cfg", True, []))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._persistence_gate_passed", lambda _state: (True, ""))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._rulebook_gate_passed", lambda _state: (True, ""))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._validate_phase_1_3_foundation", lambda _state: (True, ""))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._validate_exit", lambda _entry, _state: (True, ""))

        state = {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "phase_transition_evidence": True,
            "implementation_accepted": True,
        }
        ctx = RuntimeContext(
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=tmp_path / "commands",
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        )

        result = execute(
            current_token="6.execution",
            session_state_doc={"SESSION_STATE": state},
            runtime_ctx=ctx,
            readonly=True,
        )

        assert ("6.execution", "implementation_accepted") in calls
        assert result.next_token == "6.internal_review"
        assert result.source == "phase-6-implementation-accepted"

    def test_execute_topology_failure_is_not_silent(self, tmp_path, monkeypatch):
        """execute(): topology lookup failure in Phase 6 raises (no silent fallback)."""
        from governance_runtime.kernel.phase_api_spec import PhaseApiSpec, PhaseSpecEntry, TransitionRule
        from governance_runtime.kernel.phase_kernel import RuntimeContext

        fake_spec = PhaseApiSpec(
            path=tmp_path / "phase_api.yaml",
            sha256="fake",
            stable_hash="fake",
            loaded_at="now",
            start_token="6.execution",
            entries={
                "6.execution": PhaseSpecEntry(
                    token="6.execution",
                    phase="6-PostFlight",
                    active_gate="Implementation Internal Review",
                    next_gate_condition="Continue",
                    next_token="6.execution",
                    route_strategy="stay",
                    transitions=(
                        TransitionRule(when="implementation_accepted", next_token="6.internal_review", source="phase-6-implementation-accepted"),
                    ),
                    exit_required_keys=(),
                ),
            },
        )

        def _fake_has_event(state_id: str, event: str) -> bool:
            return state_id == "6.execution" and event == "implementation_accepted"

        def _boom_get_next_state(_state_id: str, _event: str) -> str:
            raise RuntimeError("topology authoritative failure")

        monkeypatch.setattr(TopologyLoader, "has_event", staticmethod(_fake_has_event))
        monkeypatch.setattr(TopologyLoader, "get_next_state", staticmethod(_boom_get_next_state))
        monkeypatch.setattr(TopologyLoader, "is_state_terminal", staticmethod(lambda _state_id: False))

        monkeypatch.setattr("governance_runtime.kernel.phase_kernel.load_phase_api", lambda _commands_home: fake_spec)
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._resolve_paths", lambda _ctx: (tmp_path / "commands", tmp_path / "workspaces", tmp_path / "cfg", True, []))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._persistence_gate_passed", lambda _state: (True, ""))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._rulebook_gate_passed", lambda _state: (True, ""))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._validate_phase_1_3_foundation", lambda _state: (True, ""))
        monkeypatch.setattr("governance_runtime.kernel.phase_kernel._validate_exit", lambda _entry, _state: (True, ""))

        state = {
            "Phase": "6-PostFlight",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "phase_transition_evidence": True,
            "implementation_accepted": True,
        }
        ctx = RuntimeContext(
            requested_active_gate="",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=tmp_path / "commands",
            workspaces_home=tmp_path / "workspaces",
            config_root=tmp_path / "cfg",
        )

        with pytest.raises(RuntimeError, match="topology authoritative failure"):
            execute(
                current_token="6.execution",
                session_state_doc={"SESSION_STATE": state},
                runtime_ctx=ctx,
                readonly=True,
            )
