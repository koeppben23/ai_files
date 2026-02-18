from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from governance.domain.phase_state_machine import normalize_phase_token
from governance.application.dto.phase_next_action_contract import contains_ticket_prompt


@dataclass(frozen=True)
class RoutedPhase:
    phase: str
    active_gate: str
    next_gate_condition: str
    workspace_ready: bool
    source: str


_PHASE_RANK: dict[str, int] = {
    "1": 10,
    "1.1": 11,
    "1.2": 12,
    "1.3": 13,
    "1.5": 15,
    "2": 20,
    "2.1": 21,
    "3A": 30,
    "3B-1": 31,
    "3B-2": 32,
    "4": 40,
    "5": 50,
    "5.3": 53,
    "5.4": 54,
    "5.5": 55,
    "5.6": 56,
    "6": 60,
}


def _rank(token: str) -> int:
    return _PHASE_RANK.get(token, -1)


def _session_state(session_state_document: Mapping[str, object] | None) -> Mapping[str, object]:
    if session_state_document is None:
        return {}
    candidate = session_state_document.get("SESSION_STATE")
    if isinstance(candidate, Mapping):
        return candidate
    return session_state_document


def _openapi_signal(state: Mapping[str, object]) -> bool:
    addons = state.get("AddonsEvidence")
    if isinstance(addons, Mapping):
        openapi = addons.get("openapi")
        if isinstance(openapi, Mapping) and openapi.get("detected") is True:
            return True
        if openapi is True:
            return True
    repo_caps = state.get("repo_capabilities")
    if isinstance(repo_caps, list):
        normalized = {str(item).strip().lower() for item in repo_caps}
        return "openapi" in normalized
    return False


def _workspace_ready(state: Mapping[str, object], *, repo_is_git_root: bool) -> bool:
    _ = repo_is_git_root
    for key in ("workspace_ready_gate_committed", "WorkspaceReadyGateCommitted"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _transition_has_evidence(state: Mapping[str, object]) -> bool:
    value = state.get("phase_transition_evidence")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return False


def _sanitize_ticket_progression(*, phase: str, next_gate_condition: str) -> str:
    token = normalize_phase_token(phase)
    if not token:
        return next_gate_condition
    rank = _rank(token)
    if rank < _rank("4") and contains_ticket_prompt(next_gate_condition):
        return "Proceed with current phase evidence collection; ticket input is not allowed before phase 4"
    return next_gate_condition


def route_phase(
    *,
    requested_phase: str,
    requested_active_gate: str,
    requested_next_gate_condition: str,
    session_state_document: Mapping[str, object] | None,
    repo_is_git_root: bool,
) -> RoutedPhase:
    state = _session_state(session_state_document)
    requested_phase_text = requested_phase.strip() or "1.1-Bootstrap"
    workspace_ready = _workspace_ready(state, repo_is_git_root=repo_is_git_root)

    persisted_phase = str(state.get("phase") or "").strip()
    persisted_token = normalize_phase_token(persisted_phase)

    if persisted_phase and persisted_token:
        phase_text = persisted_phase
        phase_token = persisted_token
        source = "persisted-phase"
    else:
        phase_text = requested_phase_text
        phase_token = normalize_phase_token(phase_text)
        source = "requested-bootstrap"

    blocked_tokens = {
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
    }
    if phase_token in blocked_tokens and not workspace_ready:
        return RoutedPhase(
            phase="1.1-Bootstrap",
            active_gate="Workspace Ready Gate",
            next_gate_condition="Commit workspace readiness before phase progression",
            workspace_ready=False,
            source="workspace-ready-gate",
        )

    requested_token = normalize_phase_token(requested_phase_text)
    if persisted_token and requested_token and _rank(persisted_token) > _rank(requested_token):
        return RoutedPhase(
            phase=persisted_phase,
            active_gate=str(state.get("active_gate") or requested_active_gate).strip() or requested_active_gate,
            next_gate_condition=_sanitize_ticket_progression(phase=persisted_phase, next_gate_condition=(
                str(state.get("next_gate_condition") or requested_next_gate_condition).strip() or requested_next_gate_condition
            )),
            workspace_ready=workspace_ready,
            source="monotonic-session-phase",
        )

    if persisted_token and requested_token and _rank(requested_token) - _rank(persisted_token) > 1 and not _transition_has_evidence(state):
        return RoutedPhase(
            phase=persisted_phase,
            active_gate=str(state.get("active_gate") or requested_active_gate).strip() or requested_active_gate,
            next_gate_condition="Phase transition evidence required before advancing beyond next immediate phase",
            workspace_ready=workspace_ready,
            source="phase-transition-evidence-required",
        )

    allow_bootstrap_progression = requested_token in {"2", "2.1"} and workspace_ready
    if (
        not persisted_token
        and requested_token
        and _rank(requested_token) - _rank("1.1") > 1
        and not _transition_has_evidence(state)
        and not allow_bootstrap_progression
    ):
        return RoutedPhase(
            phase="1.1-Bootstrap",
            active_gate="Workspace Ready Gate",
            next_gate_condition="Phase transition evidence required before advancing beyond next immediate phase",
            workspace_ready=workspace_ready,
            source="phase-transition-evidence-required",
        )

    if persisted_token and requested_token and _rank(requested_token) >= _rank(persisted_token):
        phase_text = requested_phase_text
        phase_token = requested_token
        source = "requested-with-evidence"

    if phase_token == "2.1" and workspace_ready and _openapi_signal(state):
        return RoutedPhase(
            phase="3A-Activation",
            active_gate="API Validation Routing",
            next_gate_condition="Route to phase 3A api validation",
            workspace_ready=True,
            source="openapi-phase-routing",
        )

    return RoutedPhase(
        phase=phase_text,
        active_gate=requested_active_gate,
        next_gate_condition=_sanitize_ticket_progression(
            phase=phase_text,
            next_gate_condition=requested_next_gate_condition,
        ),
        workspace_ready=workspace_ready,
        source=source,
    )
