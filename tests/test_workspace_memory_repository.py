from __future__ import annotations

from pathlib import Path

import pytest

from governance.infrastructure.workspace_memory_repository import WorkspaceMemoryRepository


@pytest.mark.governance
def test_workspace_memory_repository_blocks_write_without_confirmation(tmp_path: Path):
    path = tmp_path / "workspaces" / "abc" / "workspace-memory.yaml"
    repo = WorkspaceMemoryRepository(path)

    result = repo.write(
        "memory: []",
        phase="5-ImplementationQA",
        mode="user",
        phase5_approved=True,
        explicit_confirmation="",
        business_rules_executed=True,
    )

    assert result.ok is False
    assert result.reason_code == "PERSIST_CONFIRMATION_REQUIRED"
    assert not path.exists()


@pytest.mark.governance
def test_workspace_memory_repository_allows_write_with_exact_confirmation(tmp_path: Path):
    path = tmp_path / "workspaces" / "abc" / "workspace-memory.yaml"
    repo = WorkspaceMemoryRepository(path)

    result = repo.write(
        "memory: []",
        phase="5-ImplementationQA",
        mode="user",
        phase5_approved=True,
        explicit_confirmation="Persist to workspace memory: YES",
        business_rules_executed=True,
    )

    assert result.ok is True
    assert path.exists()
