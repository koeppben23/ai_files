from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bootstrap.repo_identity import derive_fingerprint, derive_repo_identity, derive_repo_root


def _git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), check=True, capture_output=True)


def test_derive_repo_root_from_subdir(tmp_path: Path):
    repo = tmp_path / "repo"
    _git_init(repo)
    subdir = repo / "nested" / "path"
    subdir.mkdir(parents=True)

    root = derive_repo_root(subdir)
    assert root == repo


def test_derive_fingerprint_is_canonical_24_hex(tmp_path: Path):
    repo = tmp_path / "repo"
    _git_init(repo)

    fingerprint = derive_fingerprint(repo)
    assert re.fullmatch(r"[0-9a-f]{24}", fingerprint)


def test_derive_repo_identity_includes_source(tmp_path: Path):
    repo = tmp_path / "repo"
    _git_init(repo)

    identity = derive_repo_identity(repo)
    assert identity is not None
    assert identity.root == repo
    assert identity.source in {"git-metadata", "env", "explicit"}
