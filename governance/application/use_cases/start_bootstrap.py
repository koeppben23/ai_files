from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from governance.application.repo_identity_service import canonicalize_origin_url, derive_repo_identity
from governance.application.ports.gateways import HostAdapter, resolve_repo_root
from governance.domain.reason_codes import BLOCKED_REPO_IDENTITY_RESOLUTION, REASON_CODE_NONE


@dataclass(frozen=True)
class StartIdentityResult:
    repo_root: Path | None
    discovery_method: str
    repo_fingerprint: str
    workspace_ready: bool
    reason_code: str
    reason: str
    canonical_remote: str | None


def _git_remote_origin(adapter: HostAdapter, repo_root: Path) -> str | None:
    argv = ("git", "-C", str(repo_root), "remote", "get-url", "origin")
    res = adapter.exec_argv(argv, cwd=repo_root, timeout_seconds=10)
    if res.exit_code != 0:
        return None
    lines = (res.stdout or "").splitlines()
    first = lines[0].strip() if lines else ""
    return first or None


def evaluate_start_identity(*, adapter: HostAdapter) -> StartIdentityResult:
    rr = resolve_repo_root(adapter=adapter, cwd=adapter.cwd())
    if not rr.is_git_root or rr.repo_root is None:
        return StartIdentityResult(
            repo_root=None,
            discovery_method=rr.source,
            repo_fingerprint="",
            workspace_ready=False,
            reason_code=BLOCKED_REPO_IDENTITY_RESOLUTION,
            reason="repo-root-not-git",
            canonical_remote=None,
        )

    repo_root = rr.repo_root
    remote = _git_remote_origin(adapter, repo_root)
    canonical_remote = canonicalize_origin_url(remote) if remote else None
    identity = derive_repo_identity(repo_root, canonical_remote=canonical_remote, git_dir=None)
    fp = (identity.fingerprint or "").strip()

    if not fp:
        return StartIdentityResult(
            repo_root=None,
            discovery_method=rr.source,
            repo_fingerprint="",
            workspace_ready=False,
            reason_code=BLOCKED_REPO_IDENTITY_RESOLUTION,
            reason="identity-bootstrap-fingerprint-missing",
            canonical_remote=canonical_remote,
        )

    return StartIdentityResult(
        repo_root=repo_root,
        discovery_method=rr.source,
        repo_fingerprint=fp,
        workspace_ready=True,
        reason_code=REASON_CODE_NONE,
        reason=REASON_CODE_NONE,
        canonical_remote=canonical_remote,
    )
