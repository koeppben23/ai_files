from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from governance.domain.phase_state_machine import normalize_phase_token, phase_rank
from governance.application.dto.phase_next_action_contract import contains_ticket_prompt


@dataclass(frozen=True)
class RoutedPhase:
    phase: str
    active_gate: str
    next_gate_condition: str
    workspace_ready: bool
    source: str


def _rank(token: str) -> int:
    return phase_rank(token)


def _session_state(session_state_document: Mapping[str, object] | None) -> Mapping[str, object]:
    if session_state_document is None:
        return {}
    candidate = session_state_document.get("SESSION_STATE")
    if isinstance(candidate, Mapping):
        return candidate
    return session_state_document


def _openapi_signal(state: Mapping[str, object]) -> bool:
    """Check for OpenAPI detection signal."""
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


def _external_api_artifacts(state: Mapping[str, object]) -> bool:
    """Check for external API artifacts provided as input."""
    scope = state.get("Scope")
    if isinstance(scope, Mapping):
        external_apis = scope.get("ExternalAPIs")
        if isinstance(external_apis, list) and len(external_apis) > 0:
            return True
    # Also check for explicit external_api_artifacts flag
    artifacts = state.get("external_api_artifacts")
    if isinstance(artifacts, list) and len(artifacts) > 0:
        return True
    if artifacts is True:
        return True
    return False


def _business_rules_scope(state: Mapping[str, object]) -> str:
    """Check business rules scope status."""
    scope = state.get("Scope")
    if isinstance(scope, Mapping):
        br = scope.get("BusinessRules")
        if isinstance(br, str):
            return br.strip().lower()
    return ""


def _business_rules_discovery_resolved(state: Mapping[str, object]) -> bool:
    """Check if Phase 1.5 decision has been resolved."""
    br_scope = _business_rules_scope(state)
    if br_scope in {"not-applicable", "extracted", "skipped"}:
        return True
    gates = state.get("Gates")
    if isinstance(gates, Mapping):
        p54 = gates.get("P5.4-BusinessRules")
        if isinstance(p54, str) and p54.strip().lower() == "not-applicable":
            return True
    return False


def _api_in_scope(state: Mapping[str, object]) -> bool:
    """Check if ANY API signals are present (external artifacts or repo-embedded specs)."""
    return _openapi_signal(state) or _external_api_artifacts(state)


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

    if phase_token == "2.1" and workspace_ready:
        if not _business_rules_discovery_resolved(state):
            return RoutedPhase(
                phase="1.5-BusinessRules",
                active_gate="Business Rules Discovery Decision",
                next_gate_condition="Resolve Phase 1.5: run business rules discovery (A) or skip (B)",
                workspace_ready=True,
                source="phase-1.5-routing-required",
            )
        if _api_in_scope(state):
            return RoutedPhase(
                phase="3A-Activation",
                active_gate="API Validation Routing",
                next_gate_condition="Route to phase 3A api validation",
                workspace_ready=True,
                source="api-phase-routing",
            )
        return RoutedPhase(
            phase="4",
            active_gate="Ticket Execution",
            next_gate_condition="No APIs in scope; proceed to ticket planning",
            workspace_ready=True,
            source="phase-2.1-to-4-no-api",
        )

    if phase_token == "1.5" and workspace_ready:
        if _api_in_scope(state):
            return RoutedPhase(
                phase="3A-Activation",
                active_gate="API Validation Routing",
                next_gate_condition="Route to phase 3A api validation",
                workspace_ready=True,
                source="phase-1.5-to-3a",
            )
        return RoutedPhase(
            phase="4",
            active_gate="Ticket Execution",
            next_gate_condition="Business rules resolved; proceed to ticket planning",
            workspace_ready=True,
            source="phase-1.5-to-4",
        )

    # Phase 3A routing: if no APIs in scope, skip directly to Phase 4
    if phase_token == "3A" and not _api_in_scope(state):
        return RoutedPhase(
            phase="4",
            active_gate="Ticket Execution",
            next_gate_condition="No API artifacts detected; proceed to ticket planning",
            workspace_ready=workspace_ready,
            source="no-api-skip-to-phase4",
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
