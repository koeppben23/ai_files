"""Session state document helpers."""

from __future__ import annotations

from typing import Any, Mapping


def session_state_root(session_state_document: Mapping[str, object] | None) -> Mapping[str, object]:
    if session_state_document is None:
        return {}
    session_state = session_state_document.get("SESSION_STATE")
    if isinstance(session_state, Mapping):
        return session_state
    return session_state_document


def phase_token(value: str) -> str:
    from governance.domain.phase_state_machine import normalize_phase_token

    return normalize_phase_token(value)


def extract_repo_identity(session_state_document: Mapping[str, object] | None) -> str:
    """Extract stable repo identity (repo_fingerprint) from SESSION_STATE.
    
    Reads multiple key variants for compatibility:
    - SESSION_STATE.RepoFingerprint (canonical)
    - SESSION_STATE.repo_fingerprint (legacy)
    - root-level RepoFingerprint
    - root-level repo_fingerprint
    """
    if session_state_document is None:
        return ""
    session_state = session_state_document.get("SESSION_STATE")
    root = session_state if isinstance(session_state, Mapping) else session_state_document
    
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = root.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = session_state_document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    
    return ""


def with_workspace_ready_gate(
    session_state_document: Mapping[str, object] | None,
    *,
    repo_fingerprint: str,
    committed: bool,
) -> Mapping[str, object] | None:
    """Write workspace ready gate state with canonical keys.
    
    Writes canonical keys (PascalCase under SESSION_STATE):
    - SESSION_STATE.RepoFingerprint
    - SESSION_STATE.WorkspaceReadyGateCommitted
    
    Also writes legacy lowercase keys for transition compatibility.
    """
    if session_state_document is None:
        state: dict[str, object] = {}
    else:
        state = dict(session_state_document)
    root = state.get("SESSION_STATE")
    if isinstance(root, Mapping):
        ss = dict(root)
        ss["RepoFingerprint"] = repo_fingerprint
        ss["WorkspaceReadyGateCommitted"] = committed
        ss["repo_fingerprint"] = repo_fingerprint
        ss["workspace_ready_gate_committed"] = committed
        ss["workspace_ready"] = committed
        state["SESSION_STATE"] = ss
        return state
    state["SESSION_STATE"] = {
        "RepoFingerprint": repo_fingerprint,
        "WorkspaceReadyGateCommitted": committed,
        "repo_fingerprint": repo_fingerprint,
        "workspace_ready_gate_committed": committed,
        "workspace_ready": committed,
    }
    state["repo_fingerprint"] = repo_fingerprint
    state["workspace_ready_gate_committed"] = committed
    state["workspace_ready"] = committed
    return state
