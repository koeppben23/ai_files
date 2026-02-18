"""Deterministic repository resolver (Git evidence only)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Mapping

from governance.domain.reason_codes import BLOCKED_EXEC_DISALLOWED, BLOCKED_REPO_IDENTITY_RESOLUTION, REASON_CODE_NONE
from governance.engine.adapters import HostAdapter
from governance.infrastructure.path_contract import PathContractError, normalize_absolute_path


_ROOT_ENV_PRIORITY: tuple[str, ...] = (
    "OPENCODE_REPO_ROOT",
    "GITHUB_WORKSPACE",
    "REPO_ROOT",
)


@dataclass(frozen=True)
class RepoRootResolutionResult:
    repo_root: Path | None
    cwd_hint: Path
    source: str
    is_git_root: bool
    reason_code: str
    git_argv: tuple[str, ...]
    exit_code: int | None
    stdout_sha256: str
    stderr_sha256: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _select_invocation_dir(env: Mapping[str, str], cwd: Path) -> tuple[Path, str]:
    for key in _ROOT_ENV_PRIORITY:
        raw = str(env.get(key, "")).strip()
        if not raw:
            continue
        try:
            return normalize_absolute_path(raw, purpose=f"env:{key}"), f"env:{key}"
        except PathContractError:
            continue
    return cwd, "cwd"


def resolve_repo_root(*, adapter: HostAdapter, cwd: Path | None = None) -> RepoRootResolutionResult:
    env = adapter.environment()
    cwd_hint = normalize_absolute_path(str(cwd if cwd is not None else adapter.cwd()), purpose="cwd_hint")
    caps = adapter.capabilities()

    if not caps.exec_allowed:
        return RepoRootResolutionResult(
            repo_root=None,
            cwd_hint=cwd_hint,
            source="exec-disabled",
            is_git_root=False,
            reason_code=BLOCKED_EXEC_DISALLOWED,
            git_argv=(),
            exit_code=None,
            stdout_sha256=_sha256_text(""),
            stderr_sha256=_sha256_text("exec disallowed"),
        )
    if not caps.git_available:
        return RepoRootResolutionResult(
            repo_root=None,
            cwd_hint=cwd_hint,
            source="git-unavailable",
            is_git_root=False,
            reason_code=BLOCKED_REPO_IDENTITY_RESOLUTION,
            git_argv=(),
            exit_code=None,
            stdout_sha256=_sha256_text(""),
            stderr_sha256=_sha256_text("git unavailable"),
        )

    invocation_dir, source = _select_invocation_dir(env, cwd_hint)
    argv: tuple[str, ...] = (
        "git",
        "-c",
        "core.quotePath=false",
        "-C",
        str(invocation_dir),
        "rev-parse",
        "--show-toplevel",
    )
    res = adapter.exec_argv(argv, cwd=invocation_dir, timeout_seconds=10)
    stdout_hash = _sha256_text(res.stdout)
    stderr_hash = _sha256_text(res.stderr)

    if res.exit_code != 0:
        return RepoRootResolutionResult(
            repo_root=None,
            cwd_hint=cwd_hint,
            source=f"{source}:git-rev-parse",
            is_git_root=False,
            reason_code=BLOCKED_REPO_IDENTITY_RESOLUTION,
            git_argv=argv,
            exit_code=res.exit_code,
            stdout_sha256=stdout_hash,
            stderr_sha256=stderr_hash,
        )

    first_line = (res.stdout or "").splitlines()
    line = first_line[0].strip() if first_line else ""
    try:
        repo_root = normalize_absolute_path(line, purpose="git.show_toplevel")
    except PathContractError:
        return RepoRootResolutionResult(
            repo_root=None,
            cwd_hint=cwd_hint,
            source=f"{source}:git-rev-parse",
            is_git_root=False,
            reason_code=BLOCKED_REPO_IDENTITY_RESOLUTION,
            git_argv=argv,
            exit_code=res.exit_code,
            stdout_sha256=stdout_hash,
            stderr_sha256=stderr_hash,
        )

    return RepoRootResolutionResult(
        repo_root=repo_root,
        cwd_hint=cwd_hint,
        source=f"{source}:git-rev-parse",
        is_git_root=True,
        reason_code=REASON_CODE_NONE,
        git_argv=argv,
        exit_code=res.exit_code,
        stdout_sha256=stdout_hash,
        stderr_sha256=stderr_hash,
    )
