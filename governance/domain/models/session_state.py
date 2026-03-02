from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CommitFlags:
    persistence_committed: bool = False
    workspace_ready_gate_committed: bool = False
    workspace_artifacts_committed: bool = False


@dataclass(frozen=True)
class PolicyMode:
    """Enforcement mode flags orthogonal to OperatingMode.

    ``principal_strict`` activates the strict-exit enforcement pipeline:
    critical criteria with missing/stale/below-threshold evidence → BLOCKED.

    Derived via ``resolve_principal_strict()`` (fail-closed: any True source → True).
    NOT coupled to addon load status.
    """

    principal_strict: bool = False


@dataclass(frozen=True)
class SessionState:
    repo_fingerprint: str
    phase: str
    mode: str
    flags: CommitFlags = field(default_factory=CommitFlags)
    loaded_rulebooks: dict[str, Any] = field(default_factory=dict)
    decision_surface: dict[str, Any] = field(default_factory=dict)
    policy_mode: PolicyMode = field(default_factory=PolicyMode)
