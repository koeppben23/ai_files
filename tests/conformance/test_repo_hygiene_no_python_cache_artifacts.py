from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "node_modules"}


def _walk_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        files.append(path)
    return files


@pytest.mark.conformance
def test_no_python_cache_artifacts_in_repo_tree() -> None:
    offenders: list[str] = []
    for path in _walk_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.is_dir() and path.name == "__pycache__":
            offenders.append(rel)
        if path.is_file() and path.suffix == ".pyc":
            offenders.append(rel)
        if path.is_dir() and path.name == ".pytest_cache":
            offenders.append(rel)
    assert not offenders, f"cache artifacts must not exist in repo: {sorted(offenders)}"
