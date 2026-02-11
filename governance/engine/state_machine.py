"""Deterministic state-machine boundary for governance engine rollout.

Wave A keeps this module as a non-live boundary that models state transitions
without mutating session artifacts or invoking downstream runtime logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineState:
    """Minimal engine state contract used by boundary tests."""

    phase: str
    active_gate: str
    mode: str
    next_gate_condition: str


def build_state(
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
) -> EngineState:
    """Create an immutable engine state with deterministic field trimming."""

    return EngineState(
        phase=phase.strip(),
        active_gate=active_gate.strip(),
        mode=mode.strip(),
        next_gate_condition=next_gate_condition.strip(),
    )


def transition_to(
    current: EngineState,
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
) -> EngineState:
    """Return next state while preserving deterministic no-op behavior.

    If all normalized fields are unchanged, the exact current state object is
    returned to support no-delta checks in later rollout phases.
    """

    candidate = build_state(
        phase=phase,
        active_gate=active_gate,
        mode=mode,
        next_gate_condition=next_gate_condition,
    )
    if candidate == current:
        return current
    return candidate
