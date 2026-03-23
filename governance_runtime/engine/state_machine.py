"""Compatibility shim for the domain phase state machine."""

from governance_runtime.domain.phase_state_machine import EnginePhaseState as EngineState
from governance_runtime.domain.phase_state_machine import build_phase_state as build_state
from governance_runtime.domain.phase_state_machine import transition_phase_state as transition_to

__all__ = ["EngineState", "build_state", "transition_to"]
