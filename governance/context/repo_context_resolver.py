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

from governance.infrastructure.path_contract import PathContractError, normalize_absolute_path


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


def _resolve_absolute_env_candidate(raw: str) -> Path | None:
    try:
        return normalize_absolute_path(raw, purpose="repo_root_env")
    except PathContractError:
        return None


def _search_parent_git_root(start: Path, *, max_parent_levels: int) -> Path | None:
    """Search parent directories deterministically for a git root.

    The search is bounded and starts at `start.parent`.
    """

    if max_parent_levels <= 0:
        return None

    current = start.parent
    levels_checked = 0
    while levels_checked < max_parent_levels:
        if _is_git_root(current):
            return current
        if current == current.parent:
            return None
        current = current.parent
        levels_checked += 1
    return None


def resolve_repo_root(
    *,
    env: Mapping[str, str],
    cwd: Path | None = None,
    search_parent_git_root: bool = False,
    max_parent_levels: int = 8,
) -> RepoRootResolutionResult:
    """Resolve repo root using Wave A parity order.

    Resolution order is strict and deterministic:
    1) first valid git root found in `_ROOT_ENV_PRIORITY`
    2) `cwd` fallback (or process cwd)

    Optional enhancement (off by default for Wave A parity):
    - if fallback cwd is not a git root and `search_parent_git_root=True`,
      walk parents up to `max_parent_levels`.
    """

    for key in _ROOT_ENV_PRIORITY:
        candidate = env.get(key)
        if not candidate:
            continue
        resolved = _resolve_absolute_env_candidate(candidate)
        if resolved is None:
            continue
        if _is_git_root(resolved):
            return RepoRootResolutionResult(repo_root=resolved, source=f"env:{key}", is_git_root=True)

    base_cwd = cwd if cwd is not None else Path.cwd()
    fallback = Path(os.path.normpath(os.path.abspath(str(base_cwd.expanduser()))))
    if search_parent_git_root and not _is_git_root(fallback):
        parent_git_root = _search_parent_git_root(fallback, max_parent_levels=max_parent_levels)
        if parent_git_root is not None:
            return RepoRootResolutionResult(
                repo_root=parent_git_root,
                source="cwd-parent-search",
                is_git_root=True,
            )
    return RepoRootResolutionResult(repo_root=fallback, source="cwd", is_git_root=_is_git_root(fallback))
