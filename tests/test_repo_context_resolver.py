from __future__ import annotations

from pathlib import Path

import pytest

from governance.context.repo_context_resolver import resolve_repo_root


def _make_git_root(path: Path) -> Path:
    """Create a minimal git-root marker for resolver tests."""

    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


@pytest.mark.governance
def test_resolver_prefers_highest_priority_env_git_root(tmp_path: Path):
    """Resolver must choose OPENCODE_REPO_ROOT before lower-priority env keys."""

    preferred = _make_git_root(tmp_path / "preferred")
    lower = _make_git_root(tmp_path / "lower")
    cwd = tmp_path / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)

    result = resolve_repo_root(
        env={
            "OPENCODE_REPO_ROOT": str(preferred),
            "OPENCODE_WORKSPACE_ROOT": str(lower),
            "REPO_ROOT": str(lower),
            "GITHUB_WORKSPACE": str(lower),
        },
        cwd=cwd,
    )

    assert result.repo_root == preferred.resolve()
    assert result.source == "env:OPENCODE_REPO_ROOT"


@pytest.mark.governance
def test_resolver_skips_non_git_env_candidate_and_uses_next_valid(tmp_path: Path):
    """Resolver must ignore invalid env candidates and continue deterministically."""

    not_git = tmp_path / "not-git"
    not_git.mkdir(parents=True, exist_ok=True)
    next_valid = _make_git_root(tmp_path / "next-valid")

    result = resolve_repo_root(
        env={
            "OPENCODE_REPO_ROOT": str(not_git),
            "OPENCODE_WORKSPACE_ROOT": str(next_valid),
        },
        cwd=tmp_path,
    )

    assert result.repo_root == next_valid.resolve()
    assert result.source == "env:OPENCODE_WORKSPACE_ROOT"


@pytest.mark.governance
def test_resolver_falls_back_to_cwd_when_no_env_candidate_is_valid(tmp_path: Path):
    """Resolver must preserve legacy cwd fallback when no git env root matches."""

    cwd = tmp_path / "cwd-fallback"
    cwd.mkdir(parents=True, exist_ok=True)

    result = resolve_repo_root(
        env={
            "OPENCODE_REPO_ROOT": str(tmp_path / "missing"),
            "REPO_ROOT": str(tmp_path / "also-missing"),
        },
        cwd=cwd,
    )

    assert result.repo_root == cwd.resolve()
    assert result.source == "cwd"
