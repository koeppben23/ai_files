from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from governance.domain.models.policy_mode import PolicyMode


@dataclass(frozen=True)
class CommitFlags:
    persistence_committed: bool = False
    workspace_ready_gate_committed: bool = False
    workspace_artifacts_committed: bool = False


@dataclass(frozen=True)
class SessionState:
    repo_fingerprint: str
    phase: str
    mode: str
    flags: CommitFlags = field(default_factory=CommitFlags)
    loaded_rulebooks: dict[str, Any] = field(default_factory=dict)
    decision_surface: dict[str, Any] = field(default_factory=dict)
    policy_mode: PolicyMode = field(default_factory=PolicyMode)
