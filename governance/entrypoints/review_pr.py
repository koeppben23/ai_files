#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from governance.contracts.enforcement import require_complete_contracts


REASON_REMOTE_UNAVAILABLE = "BLOCKED-REVIEW-REMOTE-UNAVAILABLE"
REASON_FETCH_FAILED = "BLOCKED-REVIEW-FETCH-FAILED"
REASON_BASE_UNRESOLVED = "BLOCKED-REVIEW-BASE-UNRESOLVED"
REASON_HEAD_UNRESOLVED = "BLOCKED-REVIEW-HEAD-UNRESOLVED"
REASON_MERGE_BASE_UNRESOLVED = "BLOCKED-REVIEW-MERGE-BASE-UNRESOLVED"


@dataclass(frozen=True)
class ReviewResult:
    status: str
    mode: str
    base_sha: str
    head_sha: str
    merge_base_sha: str
    files_changed: int
    reason_code: str
    message: str


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _remote_available(*, repo_root: Path, remote: str) -> bool:
    completed = _run_git(["ls-remote", "--exit-code", remote], cwd=repo_root)
    return completed.returncode == 0


def _resolve_ref(*, repo_root: Path, ref: str) -> str:
    completed = _run_git(["rev-parse", ref], cwd=repo_root)
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _count_changed_files(*, repo_root: Path, base_sha: str, head_sha: str) -> int:
    completed = _run_git(["diff", "--name-only", f"{base_sha}...{head_sha}"], cwd=repo_root)
    if completed.returncode != 0:
        return 0
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return len(lines)


def _analyze_repo(*, repo_root: Path, base_ref: str, head_ref: str, mode: str) -> ReviewResult:
    base_sha = _resolve_ref(repo_root=repo_root, ref=base_ref)
    if not base_sha:
        return ReviewResult(
            status="blocked",
            mode=mode,
            base_sha="",
            head_sha="",
            merge_base_sha="",
            files_changed=0,
            reason_code=REASON_BASE_UNRESOLVED,
            message=f"base ref could not be resolved: {base_ref}",
        )
    head_sha = _resolve_ref(repo_root=repo_root, ref=head_ref)
    if not head_sha:
        return ReviewResult(
            status="blocked",
            mode=mode,
            base_sha=base_sha,
            head_sha="",
            merge_base_sha="",
            files_changed=0,
            reason_code=REASON_HEAD_UNRESOLVED,
            message=f"head ref could not be resolved: {head_ref}",
        )

    merge_base = _run_git(["merge-base", base_sha, head_sha], cwd=repo_root)
    if merge_base.returncode != 0:
        return ReviewResult(
            status="blocked",
            mode=mode,
            base_sha=base_sha,
            head_sha=head_sha,
            merge_base_sha="",
            files_changed=0,
            reason_code=REASON_MERGE_BASE_UNRESOLVED,
            message="merge-base could not be resolved",
        )

    merge_base_sha = merge_base.stdout.strip()
    files_changed = _count_changed_files(repo_root=repo_root, base_sha=base_sha, head_sha=head_sha)
    return ReviewResult(
        status="ok",
        mode=mode,
        base_sha=base_sha,
        head_sha=head_sha,
        merge_base_sha=merge_base_sha,
        files_changed=files_changed,
        reason_code="none",
        message="review comparison prepared",
    )


def analyze_pr(*, repo_root: Path, remote: str, base_branch: str, head_ref: str) -> ReviewResult:
    enforcement = require_complete_contracts(repo_root=repo_root, required_ids=("R-REVIEW-PR-001",))
    if not enforcement.ok:
        return ReviewResult(
            status="blocked",
            mode="remote",
            base_sha="",
            head_sha="",
            merge_base_sha="",
            files_changed=0,
            reason_code=REASON_BASE_UNRESOLVED,
            message=f"{enforcement.reason}: {';'.join(enforcement.details)}",
        )

    remote_base = f"refs/remotes/{remote}/{base_branch}"
    if _remote_available(repo_root=repo_root, remote=remote):
        head_tracking = f"refs/remotes/{remote}/_review_head_{uuid.uuid4().hex[:8]}"
        fetch = _run_git(
            [
                "fetch",
                "--prune",
                remote,
                f"+refs/heads/{base_branch}:{remote_base}",
                f"+{head_ref}:{head_tracking}",
            ],
            cwd=repo_root,
        )
        if fetch.returncode != 0:
            return ReviewResult(
                status="blocked",
                mode="remote",
                base_sha="",
                head_sha="",
                merge_base_sha="",
                files_changed=0,
                reason_code=REASON_FETCH_FAILED,
                message=fetch.stderr.strip() or "remote fetch failed",
            )
        return _analyze_repo(repo_root=repo_root, base_ref=remote_base, head_ref=head_tracking, mode="remote")

    temp_dir = Path(tempfile.mkdtemp(prefix="governance-review-"))
    worktree_path = temp_dir / "worktree"
    add = _run_git(["worktree", "add", "--detach", str(worktree_path), "HEAD"], cwd=repo_root)
    if add.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ReviewResult(
            status="blocked",
            mode="isolated-local",
            base_sha="",
            head_sha="",
            merge_base_sha="",
            files_changed=0,
            reason_code=REASON_REMOTE_UNAVAILABLE,
            message="remote unavailable and isolated worktree could not be created",
        )
    try:
        local_base = f"refs/remotes/{remote}/{base_branch}"
        local_head = f"refs/remotes/{remote}/_review_head_fallback"
        fetch = _run_git(
            ["fetch", "--prune", remote, f"+refs/heads/{base_branch}:{local_base}", f"+{head_ref}:{local_head}"],
            cwd=worktree_path,
        )
        if fetch.returncode != 0:
            return ReviewResult(
                status="blocked",
                mode="isolated-local",
                base_sha="",
                head_sha="",
                merge_base_sha="",
                files_changed=0,
                reason_code=REASON_FETCH_FAILED,
                message=fetch.stderr.strip() or "isolated local fetch failed",
            )
        return _analyze_repo(
            repo_root=worktree_path,
            base_ref=local_base,
            head_ref=local_head,
            mode="isolated-local",
        )
    finally:
        _run_git(["worktree", "remove", "--force", str(worktree_path)], cwd=repo_root)
        shutil.rmtree(temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze PR comparison basis for /review")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)

    result = analyze_pr(
        repo_root=Path(args.repo_root).absolute(),
        remote=str(args.remote),
        base_branch=str(args.base_branch),
        head_ref=str(args.head_ref),
    )
    payload = {
        "status": result.status,
        "mode": result.mode,
        "base_sha": result.base_sha,
        "head_sha": result.head_sha,
        "merge_base_sha": result.merge_base_sha,
        "files_changed": result.files_changed,
        "reason_code": result.reason_code,
        "message": result.message,
    }
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if result.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
