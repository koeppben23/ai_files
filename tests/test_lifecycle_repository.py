from __future__ import annotations

from pathlib import Path

import pytest

from governance.infrastructure.lifecycle_repository import EngineLifecycleRepository


@pytest.mark.governance
def test_lifecycle_repository_stage_and_rollback(tmp_path: Path):
    paths_file = tmp_path / "governance.paths.json"
    repo = EngineLifecycleRepository(paths_file)

    staged = repo.stage_activation(engine_version="1.0.0", engine_sha256="abc", ruleset_hash="def")
    assert staged.payload["engineLifecycle"]["active"]["version"] == "1.0.0"

    rolled_back = repo.rollback(trigger="test")
    assert "engineLifecycle" in rolled_back.payload
