from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from governance.kernel.phase_kernel import RuntimeContext, api_in_scope as _api_in_scope, execute
from governance.kernel.phase_kernel import _external_api_artifacts, _openapi_signal


@dataclass(frozen=True)
class RoutedPhase:
    phase: str
    next_token: str | None
    active_gate: str
    next_gate_condition: str
    workspace_ready: bool
    source: str
    status: str = "OK"
    spec_hash: str = ""
    spec_path: str = ""
    log_paths: dict[str, str] | None = None
    event_id: str = ""


def route_phase(
    *,
    requested_phase: str,
    requested_active_gate: str,
    requested_next_gate_condition: str,
    session_state_document: Mapping[str, object] | None,
    repo_is_git_root: bool,
    live_repo_fingerprint: str | None = None,
) -> RoutedPhase:
    result = execute(
        current_token=requested_phase,
        session_state_doc=session_state_document,
        runtime_ctx=RuntimeContext(
            requested_active_gate=requested_active_gate,
            requested_next_gate_condition=requested_next_gate_condition,
            repo_is_git_root=repo_is_git_root,
            live_repo_fingerprint=live_repo_fingerprint,
        ),
    )
    return RoutedPhase(
        phase=result.phase,
        next_token=result.next_token,
        active_gate=result.active_gate,
        next_gate_condition=result.next_gate_condition,
        workspace_ready=result.workspace_ready,
        source=result.source,
        status=result.status,
        spec_hash=result.spec_hash,
        spec_path=result.spec_path,
        log_paths=result.log_paths,
        event_id=result.event_id,
    )


__all__ = [
    "RoutedPhase",
    "route_phase",
    "_api_in_scope",
    "_openapi_signal",
    "_external_api_artifacts",
]
