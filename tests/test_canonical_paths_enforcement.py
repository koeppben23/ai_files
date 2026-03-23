from __future__ import annotations

import os
from pathlib import Path

import pytest

from governance_runtime.infrastructure.fs.canonical_paths import CanonicalPathError, build_canonical_paths


def test_canonical_paths_blocks_parent_traversal(tmp_path: Path) -> None:
    commands = tmp_path / "commands"
    workspaces = tmp_path / "workspaces"
    commands.mkdir(parents=True)
    workspaces.mkdir(parents=True)
    paths = build_canonical_paths({"commandsHome": str(commands), "workspacesHome": str(workspaces)})

    with pytest.raises(CanonicalPathError):
        paths.resolve_workspace_path("88b39b036804c534a1b2c3d4", "../escape.txt")


@pytest.mark.skipif(os.name == "nt", reason="symlink behavior differs on windows without admin")
def test_canonical_paths_blocks_symlink_escape(tmp_path: Path) -> None:
    commands = tmp_path / "commands"
    workspaces = tmp_path / "workspaces"
    commands.mkdir(parents=True)
    workspaces.mkdir(parents=True)
    fp = "88b39b036804c534a1b2c3d4"
    repo_home = workspaces / fp
    repo_home.mkdir(parents=True)
    (repo_home / "logs").symlink_to(tmp_path / "outside")

    paths = build_canonical_paths({"commandsHome": str(commands), "workspacesHome": str(workspaces)})
    with pytest.raises(CanonicalPathError):
        paths.resolve_workspace_path(fp, "logs/error.log.jsonl")
