from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any

from governance.domain.phase_state_machine import normalize_phase_token, phase_rank
from governance.application.dto.phase_next_action_contract import contains_ticket_prompt

from routing.gates import (
    check_persistence_gate,
    check_rulebook_gate,
    GateResult,
)
from routing.phase_rank import is_rulebook_required_phase


@dataclass(frozen=True)
class RoutedPhase:
    phase: str
    active_gate: str
    next_gate_condition: str
    workspace_ready: bool
    source: str


def _rank(token: str) -> int:
    return phase_rank(token)


def _session_state(session_state_document: Mapping[str, object] | None) -> dict[str, Any]:
    if session_state_document is None:
        return {}
    candidate = session_state_document.get("SESSION_STATE")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    if isinstance(session_state_document, Mapping):
        return dict(session_state_document)
    return {}


def _persistence_gate_passed(state: Mapping[str, object]) -> tuple[bool, str]:
    state_dict = _session_state(state)
    result = check_persistence_gate(state_dict)
    if result.passed:
        return True, "ok"
    return False, result.blocked_reason or "Persistence gate failed"


def _rulebook_gate_passed(state: Mapping[str, object]) -> tuple[bool, str]:
    state_dict = _session_state(state)
    current_phase = _extract_phase(state_dict)
    result = check_rulebook_gate(state_dict, current_phase)
    if result.passed:
        return True, "ok"
    return False, result.blocked_reason or "Rulebook gate failed"


def _full_gate_passed(state: Mapping[str, object], *, require_rulebooks: bool = False) -> tuple[bool, str]:
    persistence_ok, persistence_reason = _persistence_gate_passed(state)
    if not persistence_ok:
        return False, persistence_reason
    
    if require_rulebooks:
        rulebooks_ok, rulebooks_reason = _rulebook_gate_passed(state)
        if not rulebooks_ok:
            return False, rulebooks_reason
    
    return True, "ok"


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


def _persistence_committed(state: Mapping[str, object]) -> bool:
    for key in ("PersistenceCommitted", "persistence_committed", "persistenceCommitted"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _workspace_artifacts_committed(state: Mapping[str, object]) -> bool:
    for key in ("WorkspaceArtifactsCommitted", "workspace_artifacts_committed"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _pointer_verified(state: Mapping[str, object]) -> bool:
    for key in ("PointerVerified", "pointer_verified"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _rulebooks_loaded(state: Mapping[str, object]) -> tuple[bool, str]:
    loaded = state.get("LoadedRulebooks")
    if not isinstance(loaded, Mapping):
        return False, "LoadedRulebooks not set"
    
    core = loaded.get("core")
    if not isinstance(core, str) or not core.strip():
        return False, "core rulebook not loaded"
    
    active_profile = state.get("ActiveProfile")
    if isinstance(active_profile, str) and active_profile.strip():
        profile = loaded.get("profile")
        if not isinstance(profile, str) or not profile.strip():
            return False, f"profile rulebook '{active_profile}' not loaded"
    
    return True, "ok"


def _extract_fingerprint(state: Mapping[str, object]) -> str:
    """Extract fingerprint from state, trying multiple key variants."""
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_phase(state: Mapping[str, object]) -> str:
    """Extract phase from state, trying multiple key variants."""
    for key in ("Phase", "phase"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _workspace_ready(
    state: Mapping[str, object],
    *,
    repo_is_git_root: bool,
    live_repo_fingerprint: str | None = None,
) -> bool:
    _ = repo_is_git_root
    gate_passed, _reason = _persistence_gate_passed(state)
    if not gate_passed:
        return False
    
    if live_repo_fingerprint is not None:
        state_fingerprint = _extract_fingerprint(state)
        if state_fingerprint and state_fingerprint != live_repo_fingerprint:
            return False
    
    return True


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
    live_repo_fingerprint: str | None = None,
) -> RoutedPhase:
    state = _session_state(session_state_document)
    requested_phase_text = requested_phase.strip() or "1.1-Bootstrap"
    workspace_ready = _workspace_ready(
        state, repo_is_git_root=repo_is_git_root, live_repo_fingerprint=live_repo_fingerprint
    )

    persisted_phase = _extract_phase(state)
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
        _, block_reason = _persistence_gate_passed(state)
        return RoutedPhase(
            phase="1.1-Bootstrap",
            active_gate="Workspace Ready Gate",
            next_gate_condition=f"BLOCKED_PERSISTENCE_FAILED: {block_reason}. Commit workspace readiness before phase progression.",
            workspace_ready=False,
            source="workspace-ready-gate",
        )

    requested_token = normalize_phase_token(requested_phase_text)
    
    if persisted_token and requested_token and _rank(requested_token) >= _rank(persisted_token):
        target_phase_token = requested_token
    else:
        target_phase_token = phase_token
    
    if is_rulebook_required_phase(target_phase_token):
        state_dict = _session_state(state)
        rulebook_gate = check_rulebook_gate(state_dict, target_phase_token)
        if not rulebook_gate.passed:
            return RoutedPhase(
                phase="1.3-RulebookLoad",
                active_gate="Rulebook Load Gate",
                next_gate_condition=f"BLOCKED_RULEBOOK_MISSING: {rulebook_gate.blocked_reason}. Load required rulebooks before Phase {target_phase_token}.",
                workspace_ready=workspace_ready,
                source="rulebook-load-gate",
            )
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
        return RoutedPhase(
            phase="3A-API-Inventory",
            active_gate="API Validation Routing",
            next_gate_condition=(
                "Execute Phase 3A API Inventory; if no APIs are detected, record not-applicable and proceed to Phase 4"
            ),
            workspace_ready=True,
            source="phase-2.1-to-3a",
        )

    if phase_token == "1.5" and workspace_ready:
        return RoutedPhase(
            phase="3A-API-Inventory",
            active_gate="API Validation Routing",
            next_gate_condition=(
                "Execute Phase 3A API Inventory; if no APIs are detected, record not-applicable and proceed to Phase 4"
            ),
            workspace_ready=True,
            source="phase-1.5-to-3a",
        )

    # Phase 3A routing: always execute 3A; if no APIs in scope, record not-applicable and skip to Phase 4
    # If APIs are in scope, route to 3B-1 for logical validation
    if phase_token == "3A":
        if not _api_in_scope(state):
            return RoutedPhase(
                phase="4",
                active_gate="Ticket Execution",
                next_gate_condition="Phase 3A completed with not-applicable (no APIs detected); proceed to ticket planning",
                workspace_ready=workspace_ready,
                source="phase-3a-not-applicable-to-phase4",
            )
        return RoutedPhase(
            phase="3B-1",
            active_gate="API Logical Validation",
            next_gate_condition="APIs detected; proceed to Phase 3B-1 logical validation",
            workspace_ready=workspace_ready,
            source="phase-3a-to-3b1",
        )

    # Phase 3B-1 → 3B-2 (contract validation)
    if phase_token == "3B-1":
        return RoutedPhase(
            phase="3B-2",
            active_gate="Contract Validation",
            next_gate_condition="Phase 3B-1 complete; proceed to Phase 3B-2 contract validation",
            workspace_ready=workspace_ready,
            source="phase-3b1-to-3b2",
        )

    # Phase 3B-2 → 4 (ticket planning)
    if phase_token == "3B-2":
        return RoutedPhase(
            phase="4",
            active_gate="Ticket Execution",
            next_gate_condition="Phase 3B-2 complete; proceed to ticket planning",
            workspace_ready=workspace_ready,
            source="phase-3b2-to-4",
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
