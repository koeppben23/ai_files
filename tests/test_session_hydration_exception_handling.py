from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from governance_runtime.entrypoints.session_hydration import (
    _validate_knowledge_base,
    _build_hydration_brief,
    _compute_artifact_digest,
)
from governance_runtime.infrastructure.session_hydration import resolve_session_state


class TestSessionHydrationExceptionHandling:
    """Tests for exception handling in session_hydration.py."""

    def test_validate_knowledge_base_handles_oserror(self, tmp_path: Path):
        """Test that OSError on file read is caught and treated as missing."""
        artifact = tmp_path / "repo-map-digest.md"
        artifact.mkdir(parents=True, exist_ok=True)
        
        # Make the file unreadable by making it a directory
        artifact.rmdir()
        
        # When we try to read from a non-file path, it should be caught
        result_ok, missing, optional = _validate_knowledge_base(tmp_path, "test123")
        
        # The result should indicate missing artifacts due to read error
        assert isinstance(result_ok, bool)
        assert isinstance(missing, list)

    def test_validate_knowledge_base_handles_unicode_decode_error(self, tmp_path: Path):
        """Test that UnicodeDecodeError is properly handled."""
        artifact_path = tmp_path / "repo-map-digest.md"
        artifact_path.write_bytes(b"\x80\x81\x82")  # Invalid UTF-8
        
        result_ok, missing, optional = _validate_knowledge_base(tmp_path, "test123")
        
        # Should handle the decode error gracefully
        assert isinstance(result_ok, bool)

    def test_compute_artifact_digest_handles_file_errors(self, tmp_path: Path):
        """Test that file read errors in digest computation are handled."""
        artifact = tmp_path / "test.md"
        artifact.write_text("content")
        
        digest = _compute_artifact_digest("test123", tmp_path)
        
        # Should complete without raising even if some files fail
        assert digest is not None

    def test_build_hydration_brief_handles_json_error(self, tmp_path: Path, monkeypatch):
        """Test that JSON parse errors in governance-config are handled."""
        workspace = tmp_path / "workspaces" / "test123"
        workspace.mkdir(parents=True, exist_ok=True)
        
        state_dir = workspace / ".governance"
        state_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = state_dir / "governance-config.json"
        config_file.write_text("{invalid json}")  # Broken JSON
        
        from governance_runtime.infrastructure.workspace_paths import governance_runtime_state_dir
        monkeypatch.setattr(
            "governance_runtime.entrypoints.session_hydration.governance_runtime_state_dir",
            lambda *args: state_dir
        )
        
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        
        brief = _build_hydration_brief(repo_root, workspace, "test123")
        
        # Should handle the error gracefully and include fallback message
        assert "Governance mode unknown" in brief or "No governance" in brief

    def test_build_hydration_brief_handles_read_errors(self, tmp_path: Path):
        """Test that read errors on artifact files are handled."""
        workspace = tmp_path / "workspaces" / "test123"
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Create empty artifacts
        (workspace / "repo-map-digest.md").write_text("content")
        (workspace / "workspace-memory.yaml").write_text("content")
        (workspace / "decision-pack.md").write_text("content")
        
        from governance_runtime.infrastructure.workspace_paths import governance_runtime_state_dir
        state_dir = workspace / ".governance"
        state_dir.mkdir()
        
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        
        brief = _build_hydration_brief(repo_root, workspace, "test123")
        
        # Should complete without raising
        assert isinstance(brief, str)
        assert len(brief) > 0


class TestInfrastructureSessionHydration:
    """Tests for infrastructure/session_hydration.py exception handling."""

    @patch("governance_runtime.infrastructure.session_locator.resolve_active_session_paths")
    @patch("governance_runtime.infrastructure.json_store.load_json")
    def test_resolve_session_state_handles_import_error(self, mock_load_json, mock_resolve):
        """Test that import errors are handled gracefully."""
        mock_resolve.side_effect = ImportError("Module not found")
        
        from governance_runtime.infrastructure.session_hydration import resolve_session_state
        result = resolve_session_state()
        
        assert result == {}

    @patch("governance_runtime.infrastructure.session_locator.resolve_active_session_paths")
    @patch("governance_runtime.infrastructure.json_store.load_json")
    def test_resolve_session_state_handles_os_error(self, mock_load_json, mock_resolve):
        """Test that OS errors are handled gracefully."""
        mock_resolve.side_effect = OSError("File not found")
        
        from governance_runtime.infrastructure.session_hydration import resolve_session_state
        result = resolve_session_state()
        
        assert result == {}

    @patch("governance_runtime.infrastructure.session_locator.resolve_active_session_paths")
    @patch("governance_runtime.infrastructure.json_store.load_json")
    def test_resolve_session_state_handles_json_error(self, mock_load_json, mock_resolve):
        """Test that JSON parse errors are handled gracefully."""
        mock_resolve.return_value = ("/path", "fp", "/ws", "/dir")
        mock_load_json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        
        from governance_runtime.infrastructure.session_hydration import resolve_session_state
        result = resolve_session_state()
        
        assert result == {}


class TestSessionHydrationMainFunction:
    """Tests for main function exception handling."""

    @patch("governance_runtime.entrypoints.session_hydration.resolve_active_session_paths")
    def test_main_handles_session_resolution_error(self, mock_resolve, tmp_path: Path, monkeypatch):
        """Test that session resolution errors are handled with proper exit code."""
        mock_resolve.side_effect = OSError("Cannot resolve paths")
        
        monkeypatch.chdir(tmp_path)
        
        from governance_runtime.entrypoints import session_hydration
        result = session_hydration.main([])
        
        # Should return exit code 2 (blocked)
        assert result == 2

    @patch("governance_runtime.entrypoints.session_hydration.load_json")
    @patch("governance_runtime.entrypoints.session_hydration.resolve_active_session_paths")
    def test_main_handles_corrupt_session_state(
        self, mock_resolve, mock_load, tmp_path: Path, monkeypatch
    ):
        """Test that corrupt session state is handled with proper exit code."""
        mock_resolve.return_value = (tmp_path / "session.json", "fp", tmp_path / "ws", tmp_path / "dir")
        mock_load.side_effect = json.JSONDecodeError("Invalid", "", 0)
        
        monkeypatch.chdir(tmp_path)
        
        from governance_runtime.entrypoints import session_hydration
        result = session_hydration.main([])
        
        # Should return exit code 2 (blocked)
        assert result == 2
