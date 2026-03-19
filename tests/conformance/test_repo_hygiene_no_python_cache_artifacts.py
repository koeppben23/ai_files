from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
def _tracked_and_unignored_repo_paths() -> list[str]:
    """Return paths known to git (tracked + untracked non-ignored)."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(REPO_ROOT),
        check=True,
        text=False,
        capture_output=True,
    )
    entries = [p.decode("utf-8", errors="replace") for p in result.stdout.split(b"\x00") if p]
    return entries


@pytest.mark.conformance
def test_no_python_cache_artifacts_in_repo_tree() -> None:
    offenders: list[str] = []
    for rel in _tracked_and_unignored_repo_paths():
        parts = rel.split("/")
        if "__pycache__" in parts:
            offenders.append(rel)
        if rel.endswith(".pyc"):
            offenders.append(rel)
        if ".pytest_cache" in parts:
            offenders.append(rel)
    assert not offenders, f"cache artifacts must not exist in repo: {sorted(offenders)}"
