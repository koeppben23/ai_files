from __future__ import annotations

from pathlib import Path

import pytest

from governance.application.use_cases.start_bootstrap import evaluate_start_identity


@pytest.mark.governance
def test_start_identity_returns_unresolved_when_cwd_is_not_git_repo(tmp_path: Path):
    non_repo = tmp_path / "backup"
    non_repo.mkdir(parents=True, exist_ok=True)

    result = evaluate_start_identity(env={}, cwd=non_repo)

    assert result.workspace_ready is False
    assert result.repo_root is None
    assert result.repo_fingerprint == ""
    assert result.reason_code == "BLOCKED-REPO-IDENTITY-RESOLUTION"


@pytest.mark.governance
def test_start_identity_derives_fingerprint_from_git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "config").write_text(
        "[remote \"origin\"]\n\turl = git@github.com:org/proj.git\n",
        encoding="utf-8",
    )

    result = evaluate_start_identity(env={"OPENCODE_REPO_ROOT": str(repo)}, cwd=repo)

    assert result.workspace_ready is True
    assert result.repo_root == repo
    assert isinstance(result.repo_fingerprint, str) and result.repo_fingerprint.strip()
    assert result.reason_code == "none"
