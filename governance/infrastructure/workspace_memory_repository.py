from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from governance.application.policies.persistence_policy import (
    ARTIFACT_WORKSPACE_MEMORY,
    PersistencePolicyInput,
    can_write,
)
from governance.infrastructure.fs_atomic import atomic_write_text


@dataclass(frozen=True)
class WorkspaceMemoryWriteResult:
    ok: bool
    reason_code: str
    reason: str


class WorkspaceMemoryRepository:
    def __init__(self, path: Path):
        self.path = path

    def write(
        self,
        content: str,
        *,
        phase: str,
        mode: str,
        phase5_approved: bool,
        explicit_confirmation: str,
        business_rules_executed: bool,
    ) -> WorkspaceMemoryWriteResult:
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
                phase=phase,
                mode=mode,
                gate_approved=phase5_approved,
                business_rules_executed=business_rules_executed,
                explicit_confirmation=explicit_confirmation,
            )
        )
        if not decision.allowed:
            return WorkspaceMemoryWriteResult(False, decision.reason_code, decision.reason)

        payload = content if content.endswith("\n") else content + "\n"
        atomic_write_text(self.path, payload)
        return WorkspaceMemoryWriteResult(True, "none", "ok")
