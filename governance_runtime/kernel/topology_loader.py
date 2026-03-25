"""Topology Loader - Operative Authority for State Machine Transitions.

This module provides topology enforcement as the operative authority
for state machine transitions. It reads from topology.yaml via SpecRegistry
and provides runtime methods for transition resolution.

Architecture:
    - topology_loader.py: State machine binding (WP2)
    - Uses SpecRegistry as single source of truth for spec loading
    - Provides fail-closed transition validation
    - Phase 6 states use topology as PRIMARY source for transitions

Usage:
    from governance_runtime.kernel.topology_loader import (
        resolve_transition,
        get_state_transitions,
        is_state_terminal,
        TopologyLoader,
    )
    
    # Get next state for an event (fail-closed)
    next_state = resolve_transition("6.execution", "implementation_accepted")
    
    # Check if state is terminal
    is_terminal = is_state_terminal("6.complete")

Integration:
    - _select_transition() in phase_kernel.py uses topology for Phase 6 states
    - Guards determine WHICH event fires, topology determines WHERE it goes
    - Non-Phase 6 states continue using phase_api.yaml guard-based logic
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from governance_runtime.kernel.spec_registry import SpecRegistry


class TopologyError(RuntimeError):
    """Base error for topology failures."""
    pass


class StateNotFoundError(TopologyError):
    """Raised when a state is not found in topology."""
    pass


class InvalidTransitionError(TopologyError):
    """Raised when a transition is invalid."""
    pass


@dataclass(frozen=True)
class TransitionDef:
    """Definition of a transition from topology.yaml."""
    id: str
    event: str
    target: str


@dataclass(frozen=True)
class StateDef:
    """Definition of a state from topology.yaml."""
    id: str
    terminal: bool
    parent: str | None
    description: str | None
    transitions: tuple[TransitionDef, ...]


class TopologyLoader:
    """Loader for topology with runtime enforcement.
    
    Provides state machine transition resolution based on topology.yaml.
    Uses SpecRegistry to access specs, ensuring consistency and fail-closed behavior.
    """

    _states: dict[str, StateDef] | None = None
    _start_state_id: str | None = None

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Ensure topology is loaded from SpecRegistry."""
        if cls._states is not None:
            return
        
        topology = SpecRegistry.get_topology()
        
        cls._start_state_id = topology.get("start_state_id", "0")
        cls._states = {}
        
        for state in topology.get("states", []):
            state_id = state.get("id", "")
            transitions = []
            for t in state.get("transitions", []):
                transitions.append(TransitionDef(
                    id=t.get("id", ""),
                    event=t.get("event", ""),
                    target=t.get("target", ""),
                ))
            
            cls._states[state_id] = StateDef(
                id=state_id,
                terminal=state.get("terminal", False),
                parent=state.get("parent"),
                description=state.get("description"),
                transitions=tuple(transitions),
            )

    @classmethod
    def reset(cls) -> None:
        """Reset the loader. For testing only."""
        cls._states = None
        cls._start_state_id = None

    @classmethod
    def get_start_state_id(cls) -> str:
        """Get the start state ID from topology."""
        cls._ensure_loaded()
        return cls._start_state_id or "0"

    @classmethod
    def get_state(cls, state_id: str) -> StateDef:
        """Get state definition by ID.
        
        Args:
            state_id: State ID (e.g., "6.approved")
            
        Returns:
            StateDef with state metadata.
            
        Raises:
            StateNotFoundError: If state not in topology.
        """
        cls._ensure_loaded()
        
        if state_id not in cls._states:
            raise StateNotFoundError(
                f"State '{state_id}' not found in topology.yaml. "
                f"Known states: {sorted(cls._states.keys())}"
            )
        
        return cls._states[state_id]

    @classmethod
    def is_state_terminal(cls, state_id: str) -> bool:
        """Check if state is terminal.
        
        Args:
            state_id: State ID
            
        Returns:
            True if state is terminal.
        """
        state = cls.get_state(state_id)
        return state.terminal

    @classmethod
    def get_state_transitions(cls, state_id: str) -> tuple[TransitionDef, ...]:
        """Get all transitions for a state.
        
        Args:
            state_id: State ID
            
        Returns:
            Tuple of TransitionDef objects.
        """
        state = cls.get_state(state_id)
        return state.transitions

    @classmethod
    def get_transition_by_event(cls, state_id: str, event: str) -> TransitionDef | None:
        """Get transition for a specific event in a state.
        
        Args:
            state_id: State ID
            event: Event name (e.g., "implementation_started")
            
        Returns:
            TransitionDef if found, None otherwise.
        """
        transitions = cls.get_state_transitions(state_id)
        
        for transition in transitions:
            if transition.event == event:
                return transition
        
        return None

    @classmethod
    def get_next_state(cls, state_id: str, event: str) -> str:
        """Get next state for an event.
        
        Args:
            state_id: Current state ID
            event: Event name
            
        Returns:
            Target state ID.
            
        Raises:
            StateNotFoundError: If current state not in topology.
            InvalidTransitionError: If no transition for event.
        """
        transition = cls.get_transition_by_event(state_id, event)
        
        if transition is None:
            raise InvalidTransitionError(
                f"No transition from state '{state_id}' for event '{event}'. "
                f"Available events: {[t.event for t in cls.get_state_transitions(state_id)]}"
            )
        
        return transition.target

    @classmethod
    def has_event(cls, state_id: str, event: str) -> bool:
        """Check if state has a transition for an event.
        
        Args:
            state_id: State ID
            event: Event name
            
        Returns:
            True if transition exists.
        """
        return cls.get_transition_by_event(state_id, event) is not None

    @classmethod
    def get_parent_state(cls, state_id: str) -> str | None:
        """Get parent state ID if any.
        
        Args:
            state_id: State ID
            
        Returns:
            Parent state ID or None.
        """
        state = cls.get_state(state_id)
        return state.parent

    @classmethod
    def is_substate(cls, state_id: str, parent_id: str) -> bool:
        """Check if state is a substate of parent.
        
        Args:
            state_id: State ID to check
            parent_id: Potential parent state ID
            
        Returns:
            True if state_id is substate of parent_id.
        """
        parent = cls.get_parent_state(state_id)
        return parent == parent_id

    @classmethod
    def get_all_states(cls) -> list[str]:
        """Get all state IDs.
        
        Returns:
            List of state IDs.
        """
        cls._ensure_loaded()
        return sorted(cls._states.keys())

    @classmethod
    def has_state(cls, state_id: str) -> bool:
        """Check if state exists in topology.
        
        Args:
            state_id: State ID
            
        Returns:
            True if state exists.
        """
        cls._ensure_loaded()
        return state_id in cls._states

    @classmethod
    def get_all_events(cls) -> list[str]:
        """Get all unique events in topology.
        
        Returns:
            List of unique event names.
        """
        cls._ensure_loaded()
        
        events = set()
        for state in cls._states.values():
            for transition in state.transitions:
                if transition.event != "default":
                    events.add(transition.event)
        
        return sorted(events)

    @classmethod
    def get_event_target_map(cls, state_id: str) -> dict[str, str]:
        """Get event-to-target mapping for a state.
        
        Args:
            state_id: State ID
            
        Returns:
            Dict mapping event names to target state IDs.
        """
        transitions = cls.get_state_transitions(state_id)
        return {t.event: t.target for t in transitions}


# ============================================================================
# Public API - Runtime Integration
# ============================================================================

def resolve_transition(state_id: str, event: str) -> str:
    """Resolve next state for an event - fail-closed.
    
    This is the PRIMARY entry point for transition resolution in the runtime.
    It validates against topology.yaml via TopologyLoader.
    
    Args:
        state_id: Current state ID
        event: Event name
        
    Returns:
        Target state ID.
        
    Raises:
        StateNotFoundError: If state not in topology.
        InvalidTransitionError: If no transition for event.
    """
    return TopologyLoader.get_next_state(state_id, event)


def validate_state_exists(state_id: str) -> StateDef:
    """Validate that a state exists in topology.
    
    Args:
        state_id: State ID
        
    Returns:
        StateDef if valid.
        
    Raises:
        StateNotFoundError: If state not in topology.
    """
    return TopologyLoader.get_state(state_id)


def is_state_reachable(state_id: str) -> bool:
    """Check if a state is reachable from start state.
    
    This performs a breadth-first search from the start state.
    
    Args:
        state_id: Target state ID
        
    Returns:
        True if state is reachable.
    """
    TopologyLoader._ensure_loaded()
    
    start_id = TopologyLoader.get_start_state_id()
    visited = set()
    queue = [start_id]
    
    while queue:
        current = queue.pop(0)
        if current == state_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        
        for transition in TopologyLoader.get_state_transitions(current):
            if transition.target not in visited:
                queue.append(transition.target)
    
    return False
