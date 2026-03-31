from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from governance_runtime.infrastructure.adapters.git.git_cli import GitCliClient
from governance_runtime.infrastructure.adapters.process.subprocess_runner import SubprocessRunner


class TestImplementStartGitAdapterIntegration:
    """Integration tests for implement_start.py GitCliClient usage."""

    @patch.object(GitCliClient, "status_porcelain")
    def test_parse_changed_files_uses_git_adapter(self, mock_status):
        """Test that _parse_changed_files_from_git_status uses GitCliClient when available."""
        mock_status.return_value = ["M  file1.py", "A  file2.py", "?? untracked.py"]
        
        from governance_runtime.entrypoints.implement_start import _parse_changed_files_from_git_status
        result = _parse_changed_files_from_git_status(Path("/test/repo"))
        
        assert mock_status.called
        assert len(result) == 3

    @patch.object(GitCliClient, "status_porcelain")
    def test_capture_repo_change_baseline_uses_git_adapter(self, mock_status):
        """Test that _capture_repo_change_baseline uses GitCliClient when available."""
        mock_status.return_value = ["M  modified.py", "?? new.py"]
        
        from governance_runtime.entrypoints.implement_start import _capture_repo_change_baseline
        result = _capture_repo_change_baseline(Path("/test/repo"))
        
        assert mock_status.called
        assert result["repo_dirty_before"] is True
        assert "modified.py" in result["tracked_changes_before"]
        assert "new.py" in result["untracked_before"]


class TestVerificationRunnerAdapterIntegration:
    """Integration tests for verification/runner.py SubprocessRunner usage."""

    @patch.object(SubprocessRunner, "run")
    def test_run_pytest_node_uses_runner(self, mock_run):
        """Test that _run_pytest_node uses SubprocessRunner when available."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        from governance_runtime.verification.runner import _run_pytest_node
        result = _run_pytest_node("python3", Path("/test/repo"), "tests/test_example.py")
        
        assert mock_run.called
        assert result is True

    @patch.object(SubprocessRunner, "run")
    def test_run_pytest_node_returns_false_on_failure(self, mock_run):
        """Test that _run_pytest_node returns False when tests fail."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        from governance_runtime.verification.runner import _run_pytest_node
        result = _run_pytest_node("python3", Path("/test/repo"), "tests/test_example.py")
        
        assert result is False


class TestEndToEndAdapterAvailability:
    """Tests to verify adapters are properly available."""

    def test_git_cli_client_importable(self):
        """Verify GitCliClient can be imported."""
        client = GitCliClient()
        assert client is not None

    def test_subprocess_runner_importable(self):
        """Verify SubprocessRunner can be imported."""
        runner = SubprocessRunner()
        assert runner is not None

    def test_git_client_resolve_repo_root(self):
        """Verify GitCliClient.resolve_repo_root works in real repo."""
        client = GitCliClient()
        root = client.resolve_repo_root(Path("/Users/koeppben/work/ai_files"))
        assert root is not None
        assert "ai_files" in str(root)

    def test_subprocess_runner_echo(self):
        """Verify SubprocessRunner can execute a simple command."""
        runner = SubprocessRunner()
        result = runner.run(["echo", "hello"])
        assert result.returncode == 0
        assert "hello" in result.stdout
