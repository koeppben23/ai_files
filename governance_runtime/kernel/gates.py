from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class GateResult:
    passed: bool
    blocked: bool
    blocked_code: str | None = None
    blocked_reason: str | None = None

    @classmethod
    def ok(cls) -> "GateResult":
        return cls(passed=True, blocked=False)

    @classmethod
    def fail(cls, code: str, reason: str) -> "GateResult":
        return cls(passed=False, blocked=True, blocked_code=code, blocked_reason=reason)


def _read_bool(state: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return None


def check_persistence_gate(state: Mapping[str, Any]) -> GateResult:
    state_view = state.get("CommitFlags") if isinstance(state.get("CommitFlags"), Mapping) else state
    persistence_committed = _read_bool(
        state_view,
        "PersistenceCommitted",
        "persistence_committed",
        "persistenceCommitted",
    )
    if persistence_committed is not True:
        return GateResult.fail("BLOCKED_PERSISTENCE_NOT_COMMITTED", "PersistenceCommitted not true")

    workspace_ready = _read_bool(state_view, "WorkspaceReadyGateCommitted", "workspace_ready_gate_committed")
    if workspace_ready is not True:
        return GateResult.fail("BLOCKED_WORKSPACE_READY_NOT_COMMITTED", "WorkspaceReadyGateCommitted not true")

    artifacts_committed = _read_bool(state_view, "WorkspaceArtifactsCommitted", "workspace_artifacts_committed")
    if artifacts_committed is not True:
        return GateResult.fail("BLOCKED_ARTIFACTS_NOT_COMMITTED", "WorkspaceArtifactsCommitted not true")

    pointer_verified = _read_bool(state_view, "PointerVerified", "pointer_verified")
    if pointer_verified is not True:
        return GateResult.fail("BLOCKED_POINTER_NOT_VERIFIED", "PointerVerified not true")

    return GateResult.ok()
