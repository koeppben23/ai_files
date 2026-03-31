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
    
    def fake_remote_available(*, repo_root: Path, remote: str) -> bool:
        return True
    
    def fake_resolve_ref(*, repo_root: Path, ref: str) -> str:
        if "refs/remotes/origin/main" in ref:
            return "a" * 40
        if "_review_head_" in ref:
            return "b" * 40
        return ""
    
    def fake_get_merge_base(*, repo_root: Path, base_sha: str, head_sha: str) -> str:
        return "c" * 40
    
    def fake_count_changed_files(*, repo_root: Path, base_sha: str, head_sha: str) -> int:
        return 2
    
    def fake_run_git_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if joined.startswith("fetch"):
            return _cp(0)
        return _cp(1, stderr="unexpected")
    
    monkeypatch.setattr(review_pr, "_remote_available", fake_remote_available)
    monkeypatch.setattr(review_pr, "_resolve_ref", fake_resolve_ref)
    monkeypatch.setattr(review_pr, "_get_merge_base", fake_get_merge_base)
    monkeypatch.setattr(review_pr, "_count_changed_files", fake_count_changed_files)
    monkeypatch.setattr(review_pr, "_run_git_command", fake_run_git_command)
    
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "ok"
    assert result.mode == "remote"
    assert result.files_changed == 2


def test_review_pr_bad_remote_fetch_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    
    def fake_remote_available(*, repo_root: Path, remote: str) -> bool:
        return True
    
    def fake_run_git_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if joined.startswith("fetch"):
            return _cp(1, stderr="network error")
        return _cp(1, stderr="unexpected")
    
    monkeypatch.setattr(review_pr, "_remote_available", fake_remote_available)
    monkeypatch.setattr(review_pr, "_run_git_command", fake_run_git_command)
    
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "blocked"
    assert result.reason_code == "BLOCKED-REVIEW-FETCH-FAILED"


def test_review_pr_corner_remote_unavailable_uses_isolated_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    
    call_count = {"count": 0}
    
    def fake_remote_available(*, repo_root: Path, remote: str) -> bool:
        return False
    
    def fake_resolve_ref(*, repo_root: Path, ref: str) -> str:
        if "refs/remotes/origin/main" in ref:
            return "a" * 40
        if "_review_head_fallback" in ref:
            return "b" * 40
        return ""
    
    def fake_get_merge_base(*, repo_root: Path, base_sha: str, head_sha: str) -> str:
        return "c" * 40
    
    def fake_count_changed_files(*, repo_root: Path, base_sha: str, head_sha: str) -> int:
        return 1
    
    def fake_run_git_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if joined.startswith("worktree add"):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return _cp(0)
            return _cp(1)
        if joined.startswith("fetch"):
            return _cp(0)
        if joined.startswith("worktree remove"):
            return _cp(0)
        return _cp(1, stderr="unexpected")
    
    monkeypatch.setattr(review_pr, "_remote_available", fake_remote_available)
    monkeypatch.setattr(review_pr, "_resolve_ref", fake_resolve_ref)
    monkeypatch.setattr(review_pr, "_get_merge_base", fake_get_merge_base)
    monkeypatch.setattr(review_pr, "_count_changed_files", fake_count_changed_files)
    monkeypatch.setattr(review_pr, "_run_git_command", fake_run_git_command)
    
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "ok"
    assert result.mode == "isolated-local"
    assert result.files_changed == 1


def test_review_pr_edge_merge_base_unresolved_blocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    
    def fake_remote_available(*, repo_root: Path, remote: str) -> bool:
        return True
    
    def fake_resolve_ref(*, repo_root: Path, ref: str) -> str:
        return "a" * 40
    
    def fake_get_merge_base(*, repo_root: Path, base_sha: str, head_sha: str) -> str:
        return ""
    
    def fake_run_git_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        if args[0] == "fetch":
            return _cp(0)
        return _cp(1, stderr="unexpected")
    
    monkeypatch.setattr(review_pr, "_remote_available", fake_remote_available)
    monkeypatch.setattr(review_pr, "_resolve_ref", fake_resolve_ref)
    monkeypatch.setattr(review_pr, "_get_merge_base", fake_get_merge_base)
    monkeypatch.setattr(review_pr, "_run_git_command", fake_run_git_command)
    
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "blocked"
    assert result.reason_code == "BLOCKED-REVIEW-MERGE-BASE-UNRESOLVED"


def test_review_pr_happy_isolated_local_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    
    def fake_remote_available(*, repo_root: Path, remote: str) -> bool:
        return False
    
    def fake_resolve_ref(*, repo_root: Path, ref: str) -> str:
        return "a" * 40
    
    def fake_get_merge_base(*, repo_root: Path, base_sha: str, head_sha: str) -> str:
        return "b" * 40
    
    def fake_count_changed_files(*, repo_root: Path, base_sha: str, head_sha: str) -> int:
        return 3
    
    def fake_run_git_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        if args[0] == "worktree":
            return _cp(0)
        if args[0] == "fetch":
            return _cp(0)
        return _cp(1)
    
    monkeypatch.setattr(review_pr, "_remote_available", fake_remote_available)
    monkeypatch.setattr(review_pr, "_resolve_ref", fake_resolve_ref)
    monkeypatch.setattr(review_pr, "_get_merge_base", fake_get_merge_base)
    monkeypatch.setattr(review_pr, "_count_changed_files", fake_count_changed_files)
    monkeypatch.setattr(review_pr, "_run_git_command", fake_run_git_command)
    
    result = review_pr.analyze_pr(repo_root=tmp_path, remote="origin", base_branch="main", head_ref="refs/heads/feat/x")
    assert result.status == "ok"
    assert result.mode == "isolated-local"
    assert result.files_changed == 3


def test_review_pr_main_happy(monkeypatch, tmp_path: Path, capsys) -> None:
    """User surface: main() outputs valid JSON payload with status and mode."""
    monkeypatch.setattr(review_pr, "require_complete_contracts", lambda repo_root, required_ids: _EnforcementOk())
    
    def fake_remote_available(*, repo_root: Path, remote: str) -> bool:
        return True
    
    def fake_resolve_ref(*, repo_root: Path, ref: str) -> str:
        if "refs/remotes/origin/main" in ref:
            return "a" * 40
        if "_review_head_" in ref:
            return "b" * 40
        return ""
    
    def fake_get_merge_base(*, repo_root: Path, base_sha: str, head_sha: str) -> str:
        return "c" * 40
    
    def fake_count_changed_files(*, repo_root: Path, base_sha: str, head_sha: str) -> int:
        return 5
    
    def fake_run_git_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        return _cp(0)
    
    monkeypatch.setattr(review_pr, "_remote_available", fake_remote_available)
    monkeypatch.setattr(review_pr, "_resolve_ref", fake_resolve_ref)
    monkeypatch.setattr(review_pr, "_get_merge_base", fake_get_merge_base)
    monkeypatch.setattr(review_pr, "_count_changed_files", fake_count_changed_files)
    monkeypatch.setattr(review_pr, "_run_git_command", fake_run_git_command)
    
    returncode = review_pr.main([
        "--repo-root", str(tmp_path),
        "--base-branch", "main",
        "--head-ref", "refs/heads/feat/x",
    ])
    
    assert returncode == 0
    
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["status"] == "ok"
    assert output["mode"] == "remote"
    assert output["files_changed"] == 5
    assert output["base_sha"] == "a" * 40
    assert output["head_sha"] == "b" * 40
    assert output["merge_base_sha"] == "c" * 40
