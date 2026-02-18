from __future__ import annotations

from pathlib import Path

import pytest

from governance.application.use_cases.start_persistence import decide_start_persistence


@pytest.mark.governance
def test_start_persistence_blocks_when_repo_not_resolved(tmp_path: Path):
    non_repo = tmp_path / "backup"
    non_repo.mkdir(parents=True, exist_ok=True)

    decision = decide_start_persistence(env={}, cwd=non_repo)

    assert decision.workspace_ready is False
    assert decision.repo_root is None
    assert decision.repo_fingerprint == ""
    assert decision.reason_code == "BLOCKED-REPO-IDENTITY-RESOLUTION"
    assert decision.reason == "repo-root-not-git"


@pytest.mark.governance
def test_start_persistence_resolves_workspace_ready_for_git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "config").write_text(
        "[remote \"origin\"]\n\turl = git@github.com:org/proj.git\n",
        encoding="utf-8",
    )

    decision = decide_start_persistence(env={"OPENCODE_REPO_ROOT": str(repo)}, cwd=repo)

    assert decision.workspace_ready is True
    assert decision.repo_root == repo
    assert isinstance(decision.repo_fingerprint, str) and decision.repo_fingerprint.strip()
    assert decision.reason_code == "none"
    assert decision.reason == "none"
