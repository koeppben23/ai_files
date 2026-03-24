"""Tests for governance-config.json materialization during bootstrap.

These tests verify that:
1. Bootstrap materializes governance-config.json if not present
2. Bootstrap does NOT overwrite existing governance-config.json (idempotency)
3. Bootstrap handles missing asset gracefully (no crash)
4. write_actions reflects the correct status
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from governance_runtime.application.use_cases.bootstrap_persistence import (
    BootstrapInput,
    BootstrapPersistenceService,
    _read_default_governance_config,
)
from governance_runtime.domain.models.binding import Binding
from governance_runtime.domain.models.layouts import WorkspaceLayout
from governance_runtime.domain.models.repo_identity import RepoIdentity


class MockFileSystem:
    """Mock filesystem for testing."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.written: dict[str, str] = {}

    def read_text(self, path: Path) -> str:
        key = str(path)
        if key in self.files:
            return self.files[key]
        raise FileNotFoundError(f"{key} not found")

    def write_text_atomic(self, path: Path, content: str) -> None:
        self.written[str(path)] = content

    def exists(self, path: Path) -> bool:
        return str(path) in self.files

    def mkdir_p(self, path: Path) -> None:
        self.files[str(path)] = ""


class MockRunner:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""
        self.last_command: list[str] = []

    def run(self, argv: list[str], env: dict[str, str] | None = None) -> MagicMock:
        self.last_command = list(argv)
        result = MagicMock()
        result.returncode = self.returncode
        result.stdout = self.stdout
        result.stderr = self.stderr
        return result


class MockLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def write(self, event: Any) -> None:
        self.events.append(event)


def make_payload(
    tmp_path: Path,
    *,
    workspace_root: Path | None = None,
    skip_artifact_backfill: bool = True,
    no_commit: bool = False,
) -> BootstrapInput:
    """Create a minimal BootstrapInput for testing."""
    if workspace_root is None:
        workspace_root = tmp_path / "workspace"

    return BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root=str(tmp_path / "repo"),
            fingerprint="abc123",
            repo_name="test-repo",
            source="test",
        ),
        binding=Binding(
            config_root=str(tmp_path / "config"),
            commands_home=str(tmp_path / "commands"),
            workspaces_home=str(tmp_path / "workspaces"),
            python_command="python",
        ),
        layout=WorkspaceLayout(
            repo_home=str(workspace_root),
            session_state_file=str(workspace_root / "SESSION_STATE.json"),
            identity_map_file=str(workspace_root / "repo-identity-map.yaml"),
            pointer_file=str(tmp_path / "config" / "opencode-session-pointer.v1"),
        ),
        required_artifacts=(),
        skip_artifact_backfill=skip_artifact_backfill,
        no_commit=no_commit,
    )


@pytest.mark.governance
def test_materializes_governance_config_when_not_present(tmp_path: Path) -> None:
    """Bootstrap materializes governance-config.json if not present."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    fs = MockFileSystem()
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)
    result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True
    assert "governance_config" in result.write_actions
    assert result.write_actions["governance_config"] == "materialized"

    config_path = workspace_root / "governance-config.json"
    assert str(config_path) in fs.written
    content = json.loads(fs.written[str(config_path)])
    assert "review" in content
    assert "pipeline" in content
    assert "regulated" in content


@pytest.mark.governance
def test_does_not_overwrite_existing_governance_config(tmp_path: Path) -> None:
    """Bootstrap does NOT overwrite existing governance-config.json (idempotency)."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)

    custom_content = json.dumps({
        "review": {
            "phase5_max_review_iterations": 99,
            "phase6_max_review_iterations": 99,
        },
        "pipeline": {
            "allow_pipeline_mode": False,
            "auto_approve_enabled": False,
        },
        "regulated": {
            "allow_auto_approve": True,
            "require_governance_mode_active": False,
        },
    }, indent=2)

    fs = MockFileSystem()
    fs.files[str(workspace_root / "governance-config.json")] = custom_content
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)
    result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True
    assert result.write_actions["governance_config"] == "present"

    config_path = workspace_root / "governance-config.json"
    assert str(config_path) not in fs.written


@pytest.mark.governance
def test_handles_missing_asset_gracefully(tmp_path: Path) -> None:
    """Bootstrap handles missing asset gracefully (no crash)."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    fs = MockFileSystem()
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)

    with patch(
        "governance_runtime.application.use_cases.bootstrap_persistence._read_default_governance_config",
        return_value="",
    ):
        result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True
    assert result.write_actions["governance_config"] == "skipped-no-asset"

    config_path = workspace_root / "governance-config.json"
    assert str(config_path) not in fs.written


@pytest.mark.governance
def test_materialize_sets_correct_write_action(tmp_path: Path) -> None:
    """write_actions reflects correct governance_config status."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    fs = MockFileSystem()
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)
    result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True
    assert "governance_config" in result.write_actions
    assert result.write_actions["governance_config"] == "materialized"


@pytest.mark.governance
def test_read_default_governance_config_returns_content(tmp_path: Path) -> None:
    """_read_default_governance_config returns the asset content."""
    content = _read_default_governance_config()
    assert content
    data = json.loads(content)
    assert "review" in data
    assert "pipeline" in data
    assert "regulated" in data


@pytest.mark.governance
def test_materialized_config_matches_default_asset(tmp_path: Path) -> None:
    """Materialized config matches the default asset content."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    fs = MockFileSystem()
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)
    result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True

    default_content = _read_default_governance_config()
    materialized_content = fs.written[str(workspace_root / "governance-config.json")]

    default_data = json.loads(default_content)
    materialized_data = json.loads(materialized_content)

    assert default_data == materialized_data


@pytest.mark.governance
def test_materialize_writes_valid_json(tmp_path: Path) -> None:
    """Materialized governance-config.json is valid JSON with all required keys."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    fs = MockFileSystem()
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)
    result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True

    config_path = workspace_root / "governance-config.json"
    content = fs.written[str(config_path)]

    data = json.loads(content)
    assert isinstance(data, dict)

    assert "review" in data
    assert "phase5_max_review_iterations" in data["review"]
    assert "phase6_max_review_iterations" in data["review"]

    assert "pipeline" in data
    assert "allow_pipeline_mode" in data["pipeline"]
    assert "auto_approve_enabled" in data["pipeline"]

    assert "regulated" in data
    assert "allow_auto_approve" in data["regulated"]
    assert "require_governance_mode_active" in data["regulated"]


@pytest.mark.governance
def test_materialize_does_not_add_schema(tmp_path: Path) -> None:
    """Materialized config does NOT include $schema (not resolvable at fp-scoped path)."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True)
    fs = MockFileSystem()
    runner = MockRunner()
    logger = MockLogger()

    payload = make_payload(tmp_path, workspace_root=workspace_root, no_commit=True)
    service = BootstrapPersistenceService(fs=fs, runner=runner, logger=logger)
    result = service.run(payload, "2024-01-01T00:00:00Z")

    assert result.ok is True

    config_path = workspace_root / "governance-config.json"
    content = fs.written[str(config_path)]

    data = json.loads(content)
    assert "$schema" not in data
