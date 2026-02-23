from typing import Any, Dict, Optional
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


def check_persistence_gate(state: Dict[str, Any]) -> GateResult:
    commit_flags = state.get("CommitFlags", {})
    
    persistence_committed = commit_flags.get("PersistenceCommitted", False)
    workspace_ready = commit_flags.get("WorkspaceReadyGateCommitted", False)
    artifacts_committed = commit_flags.get("WorkspaceArtifactsCommitted", False)
    pointer_verified = commit_flags.get("PointerVerified", False)
    
    if not persistence_committed:
        return GateResult.fail(
            "BLOCKED_PERSISTENCE_NOT_COMMITTED",
            "PersistenceCommitted must be true",
        )
    
    if not workspace_ready:
        return GateResult.fail(
            "BLOCKED_WORKSPACE_READY_NOT_COMMITTED",
            "WorkspaceReadyGateCommitted must be true",
        )
    
    if not artifacts_committed:
        return GateResult.fail(
            "BLOCKED_ARTIFACTS_NOT_COMMITTED",
            "WorkspaceArtifactsCommitted must be true",
        )
    
    if not pointer_verified:
        return GateResult.fail(
            "BLOCKED_POINTER_NOT_VERIFIED",
            "PointerVerified must be true",
        )
    
    return GateResult.ok()


def check_rulebook_gate(state: Dict[str, Any], target_phase: str) -> GateResult:
    if not is_rulebook_required_phase(target_phase):
        return GateResult.ok()
    
    loaded_rulebooks = state.get("LoadedRulebooks", {})
    core = loaded_rulebooks.get("core", [])
    
    if not core or len(core) == 0:
        return GateResult.fail(
            "BLOCKED_RULEBOOK_MISSING",
            f"Rulebooks required for target phase {target_phase}",
        )
    
    return GateResult.ok()


def check_artifacts_gate(state: Dict[str, Any]) -> GateResult:
    commit_flags = state.get("CommitFlags", {})
    artifacts_committed = commit_flags.get("WorkspaceArtifactsCommitted", False)
    
    if not artifacts_committed:
        return GateResult.fail(
            "BLOCKED_ARTIFACTS_NOT_COMMITTED",
            "Workspace artifacts must be committed before proceeding",
        )
    
    return GateResult.ok()


def check_workspace_ready_gate(state: Dict[str, Any]) -> GateResult:
    return check_persistence_gate(state)
