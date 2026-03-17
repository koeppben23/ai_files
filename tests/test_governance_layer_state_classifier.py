"""
State and Logs Classification Tests - Wave 5

Tests for:
- State file identification
- Log file location validation
- Workspace path validation

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from governance.engine.state_classifier import (
    STATE_PATTERNS,
    STATE_DIR_PATTERNS,
    LOG_PATTERNS,
    is_state_file,
    is_state_directory,
    is_log_file,
    is_workspace_path,
    is_valid_log_location,
    is_install_artifact,
)


class TestStateFileClassification:
    """Test state file identification."""

    @pytest.mark.parametrize("file", sorted(STATE_PATTERNS))
    def test_state_file_recognized(self, file: str) -> None:
        """Each state pattern must be recognized."""
        assert is_state_file(Path(file)) is True

    def test_state_files_are_frozen(self) -> None:
        """State patterns must be immutable."""
        assert isinstance(STATE_PATTERNS, frozenset)


class TestStateDirectoryClassification:
    """Test state directory identification."""

    @pytest.mark.parametrize("dir", sorted(STATE_DIR_PATTERNS))
    def test_state_directory_recognized(self, dir: str) -> None:
        """Each state directory must be recognized."""
        assert is_state_directory(Path(dir)) is True


class TestLogFileClassification:
    """Test log file identification."""

    @pytest.mark.parametrize("log", sorted(LOG_PATTERNS))
    def test_log_file_recognized(self, log: str) -> None:
        """Each log pattern must be recognized."""
        assert is_log_file(Path(log)) is True


class TestLogLocationValidation:
    """Test the hard rule: logs must only be under workspaces/<fp>/logs/"""

    def test_log_in_workspace_logs_is_valid(self) -> None:
        """Log in workspaces/<fp>/logs/ is valid."""
        path = "workspaces/abc123def456/logs/flow.log.jsonl"
        assert is_valid_log_location(path) is True

    def test_log_in_workspace_root_is_invalid(self) -> None:
        """Log directly in workspace root (without /logs/) is INVALID."""
        path = "workspaces/abc123/flow.log.jsonl"
        assert is_valid_log_location(path) is False

    def test_log_in_commands_logs_is_invalid(self) -> None:
        """Log in commands/logs/ is INVALID (not workspace)."""
        path = "commands/logs/flow.log.jsonl"
        assert is_valid_log_location(path) is False

    def test_log_in_global_logs_is_invalid(self) -> None:
        """Log in global logs/ is INVALID."""
        path = "logs/flow.log.jsonl"
        assert is_valid_log_location(path) is False

    def test_log_file_not_in_workspace_is_invalid(self) -> None:
        """Log file outside workspaces is invalid."""
        path = "some/path/flow.log.jsonl"
        assert is_valid_log_location(path) is False


class TestWorkspacePathValidation:
    """Test workspace path identification."""

    def test_path_with_workspaces_is_workspace(self) -> None:
        """Path containing workspaces/ is a workspace path."""
        path = "workspaces/abc123/logs/file.log"
        assert is_workspace_path(path) is True

    def test_path_without_workspaces_is_not_workspace(self) -> None:
        """Path without workspaces/ is not a workspace path."""
        path = "some/other/path/file.json"
        assert is_workspace_path(path) is False

    def test_commands_path_is_not_workspace(self) -> None:
        """Path under commands/ is not a workspace path."""
        path = "commands/master.md"
        assert is_workspace_path(path) is False

    def test_workspaces_substring_not_matched(self) -> None:
        """Path with 'workspaces' as substring is NOT a workspace."""
        assert is_workspace_path("tmp/myworkspaces/foo") is False
        assert is_workspace_path("abc/workspaces_backup/x") is False
        assert is_workspace_path("old_workspaces/test") is False
        """Commands path is not a workspace."""
        path = "commands/governance/file.py"
        assert is_workspace_path(path) is False


class TestInstallArtifactClassification:
    """Test install artifact identification."""

    def test_install_health_is_artifact(self) -> None:
        """INSTALL_HEALTH.json is an install artifact."""
        assert is_install_artifact("INSTALL_HEALTH.json") is True

    def test_install_manifest_is_artifact(self) -> None:
        """INSTALL_MANIFEST.json is an install artifact."""
        assert is_install_artifact("INSTALL_MANIFEST.json") is True

    def test_governance_paths_is_artifact(self) -> None:
        """governance.paths.json is an install artifact."""
        assert is_install_artifact("governance.paths.json") is True

    def test_regular_file_is_not_artifact(self) -> None:
        """Regular files are not install artifacts."""
        assert is_install_artifact("some_file.py") is False


class TestStateFileExamples:
    """Test specific state file examples."""

    def test_session_state_is_state(self) -> None:
        """SESSION_STATE.json is state."""
        assert is_state_file("SESSION_STATE.json") is True

    def test_events_is_state(self) -> None:
        """events.jsonl is state."""
        assert is_state_file("events.jsonl") is True

    def test_flow_log_is_state(self) -> None:
        """flow.log.jsonl is state."""
        assert is_state_file("flow.log.jsonl") is True

    def test_rules_md_is_not_state(self) -> None:
        """rules.md is NOT state (it's content)."""
        assert is_state_file("rules.md") is False

    def test_phase_api_is_not_state(self) -> None:
        """phase_api.yaml is NOT state (it's spec)."""
        assert is_state_file("phase_api.yaml") is False
