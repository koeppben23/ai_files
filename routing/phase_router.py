from dataclasses import dataclass
from typing import Any, Dict, Optional

from .phase_rank import phase_rank
from .gates import GateResult, check_persistence_gate, check_rulebook_gate


@dataclass
class RoutedPhase:
    phase: str
    reason: str
    blocked: bool = False
    blocked_code: Optional[str] = None
    blocked_reason: Optional[str] = None
    
    @classmethod
    def ok(cls, phase: str, reason: str) -> "RoutedPhase":
        return cls(phase=phase, reason=reason, blocked=False)
    
    @classmethod
    def blocked(cls, phase: str, reason: str, code: str) -> "RoutedPhase":
        return cls(
            phase=phase,
            reason=reason,
            blocked=True,
            blocked_code=code,
            blocked_reason=reason,
        )


def route_phase(
    session_state: Dict[str, Any],
    requested_phase: Optional[str] = None,
) -> RoutedPhase:
    persistence_gate = check_persistence_gate(session_state)
    if not persistence_gate.passed:
        return RoutedPhase.blocked(
            phase="1.1-Bootstrap",
            reason="Persistence gate failed",
            code=persistence_gate.blocked_code or "BLOCKED_PERSISTENCE",
        )
    
    current_phase = session_state.get("phase_token", "0-None")
    target_phase = requested_phase or _infer_target_phase(session_state, current_phase)
    
    rulebook_gate = check_rulebook_gate(session_state, target_phase)
    if not rulebook_gate.passed:
        return RoutedPhase.blocked(
            phase="1.3-RulebookLoad",
            reason=rulebook_gate.blocked_reason or "Rulebooks required",
            code=rulebook_gate.blocked_code or "BLOCKED_RULEBOOK",
        )
    
    return RoutedPhase.ok(phase=target_phase, reason="Routing successful")


def _infer_target_phase(state: Dict[str, Any], current: str) -> str:
    current_rank = phase_rank(current)
    
    if current_rank < phase_rank("1.1-Bootstrap"):
        return "1.1-Bootstrap"
    
    if current_rank < phase_rank("1.3-RulebookLoad"):
        return "1.3-RulebookLoad"
    
    if current_rank < phase_rank("2.1-RepoHeuristics"):
        return "2.1-RepoHeuristics"
    
    if current_rank < phase_rank("4-Ready"):
        return "4-Ready"
    
    return current
