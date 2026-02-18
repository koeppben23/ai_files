from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping

from governance.application.repo_identity_service import canonicalize_origin_url, derive_repo_identity
from governance.context.repo_context_resolver import resolve_repo_root


@dataclass(frozen=True)
class StartIdentityResult:
    repo_root: Path | None
    discovery_method: str
    repo_fingerprint: str
    workspace_ready: bool
    reason_code: str


def _resolve_git_dir(repo_root: Path) -> Path | None:
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git
    if not dot_git.is_file():
        return None
    text = dot_git.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"gitdir:\s*(.+)", text)
    if not match:
        return None
    raw = Path(match.group(1).strip())
    if not raw.is_absolute():
        raw = repo_root / raw
    return raw if raw.exists() else None


def _read_origin_remote(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_origin = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_origin = stripped == '[remote "origin"]'
            continue
        if not in_origin:
            continue
        match = re.match(r"url\s*=\s*(.+)", stripped)
        if match:
            return match.group(1).strip()
    return None


def evaluate_start_identity(*, env: Mapping[str, str], cwd: Path) -> StartIdentityResult:
    repo_context = resolve_repo_root(env=env, cwd=cwd, search_parent_git_root=True)
    if not repo_context.is_git_root:
        return StartIdentityResult(
            repo_root=None,
            discovery_method=repo_context.source,
            repo_fingerprint="",
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
        )

    repo_root = repo_context.repo_root
    git_dir = _resolve_git_dir(repo_root)
    if git_dir is None:
        return StartIdentityResult(
            repo_root=repo_root,
            discovery_method=repo_context.source,
            repo_fingerprint="",
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
        )

    remote = _read_origin_remote(git_dir / "config")
    canonical_remote = canonicalize_origin_url(remote) if remote else None
    identity = derive_repo_identity(repo_root, canonical_remote=canonical_remote, git_dir=git_dir)
    if not identity.fingerprint:
        return StartIdentityResult(
            repo_root=repo_root,
            discovery_method=repo_context.source,
            repo_fingerprint="",
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
        )

    return StartIdentityResult(
        repo_root=repo_root,
        discovery_method=repo_context.source,
        repo_fingerprint=identity.fingerprint,
        workspace_ready=True,
        reason_code="none",
    )
