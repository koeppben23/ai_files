from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast
import re


PhaseToken = Literal[
    "1",
    "1.1",
    "1.2",
    "1.3",
    "1.5",
    "2",
    "2.1",
    "3A",
    "3B-1",
    "3B-2",
    "4",
    "5",
    "5.3",
    "5.4",
    "5.5",
    "5.6",
    "6",
    "unknown",
]


_PHASE_TOKEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("3B-2", r"^3B-2"),
    ("3B-1", r"^3B-1"),
    ("3A", r"^3A"),
    ("2.1", r"^2\.1"),
    ("1.5", r"^1\.5"),
    ("1.3", r"^1\.3"),
    ("1.2", r"^1\.2"),
    ("1.1", r"^1\.1"),
    ("6", r"^6(?:\b|-)"),
    ("5.6", r"^5\.6"),
    ("5.5", r"^5\.5"),
    ("5.4", r"^5\.4"),
    ("5.3", r"^5\.3"),
    ("5", r"^5(?:\b|-)"),
    ("4", r"^4(?:\b|-)"),
    ("2", r"^2(?:\b|-)"),
    ("1", r"^1(?:\b|-)"),
)


@dataclass(frozen=True)
class EnginePhaseState:
    phase: str
    active_gate: str
    mode: str
    next_gate_condition: str


@dataclass(frozen=True)
class PhaseActionPolicy:
    phase_token: PhaseToken
    ticket_required_allowed: bool


def normalize_phase_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().upper()
    if not normalized:
        return ""
    for token, pattern in _PHASE_TOKEN_PATTERNS:
        if re.match(pattern, normalized):
            return token
    return ""


def phase_requires_ticket_input(phase_token: str) -> bool:
    match = re.match(r"^(\d+)", phase_token)
    if match is None:
        return False
    return int(match.group(1)) >= 4


def resolve_phase_policy(phase_value: object) -> PhaseActionPolicy:
    token = normalize_phase_token(phase_value)
    if not token:
        return PhaseActionPolicy(phase_token="unknown", ticket_required_allowed=False)
    return PhaseActionPolicy(
        phase_token=cast(PhaseToken, token),
        ticket_required_allowed=phase_requires_ticket_input(token),
    )


def build_phase_state(
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
) -> EnginePhaseState:
    return EnginePhaseState(
        phase=phase.strip(),
        active_gate=active_gate.strip(),
        mode=mode.strip(),
        next_gate_condition=next_gate_condition.strip(),
    )


def transition_phase_state(
    current: EnginePhaseState,
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
) -> EnginePhaseState:
    candidate = build_phase_state(
        phase=phase,
        active_gate=active_gate,
        mode=mode,
        next_gate_condition=next_gate_condition,
    )
    if candidate == current:
        return current
    return candidate
