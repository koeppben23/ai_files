"""Tests for workspace_resolver module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestResolveWorkspaceDirFromPointer:
    """Tests for resolve_workspace_dir_from_pointer."""

    def test_returns_none_when_no_fingerprint(self, tmp_path: Path) -> None:
        """Returns None when pointer has no fingerprint."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_pointer
        
        pointer = {"schema": "opencode-session-pointer.v1"}
        result = resolve_workspace_dir_from_pointer(tmp_path, pointer)
        assert result is None

    def test_uses_active_repo_fingerprint(self, tmp_path: Path) -> None:
        """Uses activeRepoFingerprint to build workspace path."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_pointer
        
        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": "abc123",
        }
        result = resolve_workspace_dir_from_pointer(tmp_path, pointer)
        assert result == tmp_path / "workspaces" / "abc123"

    def test_uses_legacy_active_session_state_file(self, tmp_path: Path) -> None:
        """Falls back to activeSessionStateFile parent for legacy pointers."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_pointer
        
        session_file = tmp_path / "workspaces" / "legacy" / "SESSION_STATE.json"
        session_file.parent.mkdir(parents=True)
        session_file.write_text("{}", encoding="utf-8")
        
        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(session_file),
        }
        result = resolve_workspace_dir_from_pointer(tmp_path, pointer)
        assert result == session_file.parent

    def test_relative_session_state_file_returns_none(self, tmp_path: Path) -> None:
        """Relative activeSessionStateFile returns None."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_pointer
        
        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": "relative/path/SESSION_STATE.json",
        }
        result = resolve_workspace_dir_from_pointer(tmp_path, pointer)
        assert result is None


class TestResolveWorkspaceDirFromState:
    """Tests for resolve_workspace_dir_from_state."""

    def test_returns_none_when_no_fingerprint(self, tmp_path: Path) -> None:
        """Returns None when state has no fingerprint."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_state
        
        state = {"Phase": "5"}
        result = resolve_workspace_dir_from_state(state)
        assert result is None

    def test_uses_repo_fingerprint(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses repo_fingerprint from state."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_state
        
        workspaces_home = tmp_path / "workspaces"
        workspaces_home.mkdir(parents=True)
        
        paths_config = {
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "configRoot": str(tmp_path),
                "workspacesHome": str(workspaces_home),
                "commandsHome": str(tmp_path / "commands"),
                "pythonCommand": "python3",
            }
        }
        (tmp_path / "governance.paths.json").write_text(json.dumps(paths_config), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(tmp_path))
        
        state = {"repo_fingerprint": "xyz789", "Phase": "5"}
        result = resolve_workspace_dir_from_state(state)
        assert result == workspaces_home / "xyz789"

    def test_uses_repo_fingerprint_capital(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Uses RepoFingerprint (capital) from state."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_state
        
        workspaces_home = tmp_path / "workspaces"
        workspaces_home.mkdir(parents=True)
        
        paths_config = {
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "configRoot": str(tmp_path),
                "workspacesHome": str(workspaces_home),
                "commandsHome": str(tmp_path / "commands"),
                "pythonCommand": "python3",
            }
        }
        (tmp_path / "governance.paths.json").write_text(json.dumps(paths_config), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(tmp_path))
        
        state = {"RepoFingerprint": "abc123", "Phase": "5"}
        result = resolve_workspace_dir_from_state(state)
        assert result == workspaces_home / "abc123"

    def test_repo_fingerprint_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """RepoFingerprint takes precedence (checked first in iteration order)."""
        from governance_runtime.infrastructure.workspace_resolver import resolve_workspace_dir_from_state
        
        workspaces_home = tmp_path / "workspaces"
        workspaces_home.mkdir(parents=True)
        
        paths_config = {
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "configRoot": str(tmp_path),
                "workspacesHome": str(workspaces_home),
                "commandsHome": str(tmp_path / "commands"),
                "pythonCommand": "python3",
            }
        }
        (tmp_path / "governance.paths.json").write_text(json.dumps(paths_config), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(tmp_path))
        
        state = {"RepoFingerprint": "upper", "repo_fingerprint": "lower", "Phase": "5"}
        result = resolve_workspace_dir_from_state(state)
        assert result == workspaces_home / "upper"
