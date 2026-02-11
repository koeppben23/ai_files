"""Deterministic repository context resolver (Wave A parity skeleton).

This module centralizes repo-root resolution logic without changing behavior:
- prefer explicit environment roots in deterministic order,
- accept only candidates that are git roots,
- fall back to current working directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


_ROOT_ENV_PRIORITY: tuple[str, ...] = (
    "OPENCODE_REPO_ROOT",
    "OPENCODE_WORKSPACE_ROOT",
    "REPO_ROOT",
    "GITHUB_WORKSPACE",
)


@dataclass(frozen=True)
class RepoRootResolutionResult:
    """Resolved repository root plus deterministic source metadata."""

    repo_root: Path
    source: str
    is_git_root: bool


def _is_git_root(path: Path) -> bool:
    """Return True when the candidate path exists and contains a .git entry."""

    return path.exists() and (path / ".git").exists()


def resolve_repo_root(
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> RepoRootResolutionResult:
    """Resolve repo root using Wave A parity order.

    Resolution order is strict and deterministic:
    1) first valid git root found in `_ROOT_ENV_PRIORITY`
    2) `cwd` fallback (or process cwd)
    """

    env_view = env if env is not None else os.environ
    for key in _ROOT_ENV_PRIORITY:
        candidate = env_view.get(key)
        if not candidate:
            continue
        resolved = Path(candidate).expanduser().resolve()
        if _is_git_root(resolved):
            return RepoRootResolutionResult(repo_root=resolved, source=f"env:{key}", is_git_root=True)

    fallback = (cwd if cwd is not None else Path.cwd()).resolve()
    return RepoRootResolutionResult(repo_root=fallback, source="cwd", is_git_root=_is_git_root(fallback))
