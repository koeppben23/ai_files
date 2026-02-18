from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from governance.application.ports.gateways import HostAdapter
from governance.application.use_cases.start_bootstrap import evaluate_start_identity


@dataclass(frozen=True)
class StartPersistenceDecision:
    repo_root: Path | None
    repo_fingerprint: str
    discovery_method: str
    workspace_ready: bool
    reason_code: str
    reason: str


def decide_start_persistence(*, adapter: HostAdapter) -> StartPersistenceDecision:
    identity = evaluate_start_identity(adapter=adapter)
    repo_fp = identity.repo_fingerprint.strip()
    if identity.repo_root is None:
        return StartPersistenceDecision(
            repo_root=None,
            repo_fingerprint="",
            discovery_method=identity.discovery_method,
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
            reason="repo-root-not-git",
        )
    if not repo_fp or not identity.workspace_ready:
        return StartPersistenceDecision(
            repo_root=identity.repo_root,
            repo_fingerprint="",
            discovery_method=identity.discovery_method,
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
            reason="identity-bootstrap-fingerprint-missing",
        )
    return StartPersistenceDecision(
        repo_root=identity.repo_root,
        repo_fingerprint=repo_fp,
        discovery_method=identity.discovery_method,
        workspace_ready=True,
        reason_code="none",
        reason="none",
    )
