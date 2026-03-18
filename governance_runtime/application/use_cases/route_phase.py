from __future__ import annotations

from dataclasses import dataclass

from governance_runtime.domain.policies.gate_policy import persistence_gate, rulebook_gate
from governance_runtime.domain.policies.phase_policy import normalize_phase_token


@dataclass(frozen=True)
class RoutedPhase:
    phase: str
    blocked_code: str | None
    reason: str
    next_action: str


@dataclass(frozen=True)
class RoutePhaseInput:
    requested_phase: str
    target_phase: str | None
    loaded_rulebooks: dict[str, object]
    persistence_state: dict[str, object]
    active_profile: str | None = None
    addons_evidence: dict[str, object] | None = None


class RoutePhaseService:
    def run(self, payload: RoutePhaseInput) -> RoutedPhase:
        target = normalize_phase_token(payload.target_phase or payload.requested_phase)

        persistence = persistence_gate(payload.persistence_state)
        if not persistence.ok:
            return RoutedPhase(
                phase=target,
                blocked_code=persistence.code,
                reason=persistence.reason,
                next_action="fix-persistence",
            )

        rulebooks = rulebook_gate(
            target_phase=target,
            loaded_rulebooks=payload.loaded_rulebooks,
            active_profile=payload.active_profile,
            addons_evidence=payload.addons_evidence,
        )
        if not rulebooks.ok:
            return RoutedPhase(
                phase=target,
                blocked_code=rulebooks.code,
                reason=rulebooks.reason,
                next_action="load-rulebooks",
            )

        return RoutedPhase(phase=target, blocked_code=None, reason="ok", next_action="continue")
