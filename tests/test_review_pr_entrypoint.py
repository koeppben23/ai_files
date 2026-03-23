from __future__ import annotations

import json
import subprocess
from pathlib import Path

from governance_runtime.entrypoints import review_pr


class _EnforcementOk:
    ok = True
    reason = "ready"
    details = ()


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_review_pr_happy_remote_first(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    def fake_run(args: list[str], *, cwd: Path):
        joined = " ".join(args)
        if joined.startswith("ls-remote"):
            return _cp(0, "ok")
        if joined.startswith("fetch"):
            return _cp(0)
        if joined.startswith("rev-parse refs/remotes/origin/main"):
            return _cp(0, "a" * 40)
        if "_review_head_" in joined and joined.startswith("rev-parse"):
            return _cp(0, "b" * 40)
        if joined.startswith("merge-base"):
            return _cp(0, "c" * 40)
        if joined.startswith("diff --name-only"):
            return _cp(0, "a.py\nb.py\n")
        return _cp(1, stderr="unexpected")

    monkeypatch.setattr(review_pr, "_run_git", fake_run)
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "ok"
    assert result.mode == "remote"
    assert result.files_changed == 2


def test_review_pr_bad_remote_fetch_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    def fake_run(args: list[str], *, cwd: Path):
        joined = " ".join(args)
        if joined.startswith("ls-remote"):
            return _cp(0, "ok")
        if joined.startswith("fetch"):
            return _cp(1, stderr="network error")
        return _cp(1, stderr="unexpected")

    monkeypatch.setattr(review_pr, "_run_git", fake_run)
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "blocked"
    assert result.reason_code == "BLOCKED-REVIEW-FETCH-FAILED"


def test_review_pr_corner_remote_unavailable_uses_isolated_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    def fake_run(args: list[str], *, cwd: Path):
        joined = " ".join(args)
        if joined.startswith("ls-remote"):
            return _cp(2, stderr="offline")
        if joined.startswith("worktree add"):
            return _cp(0)
        if joined.startswith("fetch"):
            return _cp(0)
        if joined.startswith("rev-parse refs/remotes/origin/main"):
            return _cp(0, "a" * 40)
        if joined.startswith("rev-parse refs/remotes/origin/_review_head_fallback"):
            return _cp(0, "b" * 40)
        if joined.startswith("merge-base"):
            return _cp(0, "c" * 40)
        if joined.startswith("diff --name-only"):
            return _cp(0, "x.py\n")
        if joined.startswith("worktree remove"):
            return _cp(0)
        return _cp(1, stderr="unexpected")

    monkeypatch.setattr(review_pr, "_run_git", fake_run)
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "ok"
    assert result.mode == "isolated-local"


def test_review_pr_edge_merge_base_unresolved_blocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    def fake_run(args: list[str], *, cwd: Path):
        joined = " ".join(args)
        if joined.startswith("ls-remote"):
            return _cp(0, "ok")
        if joined.startswith("fetch"):
            return _cp(0)
        if joined.startswith("rev-parse refs/remotes/origin/main"):
            return _cp(0, "a" * 40)
        if "_review_head_" in joined and joined.startswith("rev-parse"):
            return _cp(0, "b" * 40)
        if joined.startswith("merge-base"):
            return _cp(1, stderr="no merge base")
        return _cp(1, stderr="unexpected")

    monkeypatch.setattr(review_pr, "_run_git", fake_run)
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "blocked"
    assert result.reason_code == "BLOCKED-REVIEW-MERGE-BASE-UNRESOLVED"


def test_review_pr_main_happy(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    monkeypatch.setattr(
        review_pr,
        "analyze_pr",
        lambda repo_root, remote, base_branch, head_ref: review_pr.ReviewResult(
            status="ok",
            mode="remote",
            base_sha="a" * 40,
            head_sha="b" * 40,
            merge_base_sha="c" * 40,
            files_changed=3,
            reason_code="none",
            message="review comparison prepared",
        ),
    )
    rc = review_pr.main([
        "--head-ref",
        "refs/heads/feat/x",
        "--repo-root",
        str(tmp_path),
    ])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["status"] == "ok"
