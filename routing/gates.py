from typing import Any, Mapping, Optional
from dataclasses import dataclass

from .phase_rank import phase_rank, is_rulebook_required_phase


@dataclass
class GateResult:
    passed: bool
    blocked: bool
    blocked_code: Optional[str] = None
    blocked_reason: Optional[str] = None
    
    @classmethod
    def ok(cls) -> "GateResult":
        return cls(passed=True, blocked=False)
    
    @classmethod
    def fail(cls, code: str, reason: str) -> "GateResult":
        return cls(passed=False, blocked=True, blocked_code=code, blocked_reason=reason)


def _read_bool(state: Mapping[str, Any], *keys: str) -> Optional[bool]:
    for key in keys:
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return None


def _state_view(state: Mapping[str, Any]) -> Mapping[str, Any]:
    commit_flags = state.get("CommitFlags")
    if isinstance(commit_flags, Mapping):
        return commit_flags
    return state


def check_persistence_gate(state: Mapping[str, Any]) -> GateResult:
    state_view = _state_view(state)
    persistence_committed = _read_bool(
        state_view,
        "PersistenceCommitted",
        "persistence_committed",
        "persistenceCommitted",
    )
    if persistence_committed is not True:
        return GateResult.fail("BLOCKED_PERSISTENCE_NOT_COMMITTED", "PersistenceCommitted not true")

    workspace_ready = _read_bool(
        state_view,
        "WorkspaceReadyGateCommitted",
        "workspace_ready_gate_committed",
    )
    if workspace_ready is None:
        return GateResult.fail("BLOCKED_WORKSPACE_READY_NOT_SET", "WorkspaceReadyGateCommitted not set")
    if workspace_ready is not True:
        return GateResult.fail(
            "BLOCKED_WORKSPACE_READY_NOT_COMMITTED",
            "WorkspaceReadyGateCommitted not true",
        )

    artifacts_committed = _read_bool(
        state_view,
        "WorkspaceArtifactsCommitted",
        "workspace_artifacts_committed",
    )
    if artifacts_committed is not True:
        return GateResult.fail("BLOCKED_ARTIFACTS_NOT_COMMITTED", "WorkspaceArtifactsCommitted not true")

    pointer_verified = _read_bool(state_view, "PointerVerified", "pointer_verified")
    if pointer_verified is not True:
        return GateResult.fail("BLOCKED_POINTER_NOT_VERIFIED", "PointerVerified not true")

    return GateResult.ok()


def check_rulebook_gate(state: Mapping[str, Any], target_phase: str) -> GateResult:
    if target_phase and not is_rulebook_required_phase(target_phase):
        return GateResult.ok()

    loaded_rulebooks = state.get("LoadedRulebooks")
    if not isinstance(loaded_rulebooks, Mapping):
        return GateResult.fail("BLOCKED_RULEBOOK_MISSING", "LoadedRulebooks not set")

    core = loaded_rulebooks.get("core")
    if not isinstance(core, str) or not core.strip():
        return GateResult.fail("BLOCKED_RULEBOOK_MISSING", "core rulebook not loaded")

    active_profile = state.get("ActiveProfile")
    if isinstance(active_profile, str) and active_profile.strip():
        profile = loaded_rulebooks.get("profile")
        if not isinstance(profile, str) or not profile.strip():
            return GateResult.fail(
                "BLOCKED_RULEBOOK_MISSING",
                f"profile rulebook '{active_profile}' not loaded",
            )

    return GateResult.ok()


def check_artifacts_gate(state: Mapping[str, Any]) -> GateResult:
    state_view = _state_view(state)
    artifacts_committed = _read_bool(
        state_view,
        "WorkspaceArtifactsCommitted",
        "workspace_artifacts_committed",
    )

    if artifacts_committed is not True:
        return GateResult.fail(
            "BLOCKED_ARTIFACTS_NOT_COMMITTED",
            "Workspace artifacts must be committed before proceeding",
        )
    
    return GateResult.ok()


def check_workspace_ready_gate(state: Mapping[str, Any]) -> GateResult:
    return check_persistence_gate(state)
