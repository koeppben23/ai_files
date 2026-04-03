from __future__ import annotations

import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from governance_runtime.infrastructure.adapters.git.git_cli import (
    GitCliClient,
    resolve_repo_root,
    is_inside_work_tree,
    get_origin_remote,
    get_config,
    status_porcelain,
    rev_parse,
    merge_base,
    diff_name_only,
    ls_remote,
    is_safe_directory,
    get_safe_directories,
)


class TestGitCliClientHappy:
    """Happy path tests for GitCliClient."""

    @pytest.fixture
    def client(self):
        return GitCliClient()

    @patch("subprocess.run")
    def test_resolve_repo_root_success(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="/repo/path\n")
        result = client.resolve_repo_root(Path("/some/dir"))
        assert result == Path("/repo/path")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_resolve_repo_root_not_a_repo(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = client.resolve_repo_root(Path("/some/dir"))
        assert result is None

    @patch("subprocess.run")
    def test_is_inside_work_tree_true(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        result = client.is_inside_work_tree(Path("/repo"))
        assert result is True

    @patch("subprocess.run")
    def test_is_inside_work_tree_false(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="false\n")
        result = client.is_inside_work_tree(Path("/repo"))
        assert result is False

    @patch("subprocess.run")
    def test_get_origin_remote_success(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="https://github.com/user/repo.git\n")
        result = client.get_origin_remote(Path("/repo"))
        assert result == "https://github.com/user/repo.git"

    @patch("subprocess.run")
    def test_get_origin_remote_no_remote(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=128, stderr="fatal: remote origin not found")
        result = client.get_origin_remote(Path("/repo"))
        assert result is None

    @patch("subprocess.run")
    def test_get_config_local(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        result = client.get_config("core.longpaths", Path("/repo"), scope="local")
        assert result == "true"

    @patch("subprocess.run")
    def test_get_config_not_set(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stderr="key does not exist")
        result = client.get_config("core.nonexistent", Path("/repo"))
        assert result is None

    @patch("subprocess.run")
    def test_status_porcelain_clean(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = client.status_porcelain(Path("/repo"))
        assert result == []

    @patch("subprocess.run")
    def test_status_porcelain_with_changes(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="M  modified.py\nA  added.py\n?? untracked.py\n"
        )
        result = client.status_porcelain(Path("/repo"))
        assert len(result) == 3
        assert "M  modified.py" in result
        assert "A  added.py" in result
        assert "?? untracked.py" in result

    @patch("subprocess.run")
    def test_rev_parse_success(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123def\n")
        result = client.rev_parse(["HEAD"], Path("/repo"))
        assert result == "abc123def"

    @patch("subprocess.run")
    def test_merge_base_success(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        result = client.merge_base("main", "feature", Path("/repo"))
        assert result == "abc123"

    @patch("subprocess.run")
    def test_diff_name_only(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="file1.py\nfile2.py\n"
        )
        result = client.diff_name_only("HEAD", None, Path("/repo"))
        assert result == ["file1.py", "file2.py"]

    @patch("subprocess.run")
    def test_ls_remote(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc123\trefs/heads/main\ndef456\trefs/heads/develop\n"
        )
        result = client.ls_remote("origin", None, Path("/repo"))
        assert len(result) == 2

    @patch("subprocess.run")
    def test_is_safe_directory_wildcard(self, mock_run, client):
        # Wildcard * means everything is safe
        mock_run.return_value = MagicMock(returncode=0, stdout="*\n")
        result = client.is_safe_directory(Path("/any/path"))
        assert result is True

    @patch("subprocess.run")
    def test_is_safe_directory_exact_match(self, mock_run, client):
        # Exact match in safe.directory
        mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
        result = client.is_safe_directory(Path("/repo"))
        assert result is True

    @patch("subprocess.run")
    def test_is_safe_directory_no_config(self, mock_run, client):
        # No safe.directory config at all - defaults to safe
        mock_run.return_value = MagicMock(returncode=1, stderr="key does not exist")
        result = client.is_safe_directory(Path("/repo"))
        assert result is True

    @patch("subprocess.run")
    def test_is_safe_directory_not_configured(self, mock_run, client):
        # Directory not in safe.directory list
        mock_run.return_value = MagicMock(returncode=0, stdout="/other/repo\n")
        result = client.is_safe_directory(Path("/repo"))
        assert result is False

    @patch("subprocess.run")
    def test_is_safe_directory_prefix_match(self, mock_run, client):
        # Config path is prefix of checked path
        mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
        result = client.is_safe_directory(Path("/repo/subdir"))
        assert result is True

    @patch("subprocess.run")
    def test_get_safe_directories(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/path/to/repo\n/another/repo\n"
        )
        result = client.get_safe_directories(Path("/repo"))
        assert result == ["/path/to/repo", "/another/repo"]


class TestGitCliClientBad:
    """Bad path tests for GitCliClient."""

    @pytest.fixture
    def client(self):
        return GitCliClient()

    @patch("subprocess.run")
    def test_resolve_repo_root_timeout(self, mock_run, client):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)
        result = client.resolve_repo_root(Path("/repo"))
        assert result is None

    @patch("subprocess.run")
    def test_resolve_repo_root_empty_output(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = client.resolve_repo_root(Path("/repo"))
        assert result is None

    @patch("subprocess.run")
    def test_get_origin_remote_empty_output(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = client.get_origin_remote(Path("/repo"))
        assert result is None

    @patch("subprocess.run")
    def test_merge_base_no_common_base(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=1, stderr="fatal: merge-base not found"
        )
        result = client.merge_base("main", "feature", Path("/repo"))
        assert result is None

    @patch("subprocess.run")
    def test_diff_name_only_error(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=128, stderr="not a git repository"
        )
        result = client.diff_name_only("HEAD", "main", Path("/repo"))
        assert result == []

    @patch("subprocess.run")
    def test_ls_remote_error(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=128, stderr="fatal: remote origin not found"
        )
        result = client.ls_remote("nonexistent", None, Path("/repo"))
        assert result == []


class TestGitCliClientCorner:
    """Corner case tests for GitCliClient."""

    @pytest.fixture
    def client(self):
        return GitCliClient()

    @patch("subprocess.run")
    def test_resolve_repo_root_none_cwd(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="/current/repo\n")
        result = client.resolve_repo_root(None)
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("cwd") is None

    @patch("subprocess.run")
    def test_get_config_with_global_scope(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        result = client.get_config("core.longpaths", None, scope="global")
        # The command should include --global flag (not just "global" as positional)
        call_cmd = mock_run.call_args[0][0]  # First positional arg is the command list
        assert "--global" in call_cmd

    @patch("subprocess.run")
    def test_status_porcelain_with_special_chars(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="M  path/with spaces.py\n"
        )
        result = client.status_porcelain(Path("/repo"))
        assert "M  path/with spaces.py" in result

    @patch("subprocess.run")
    def test_get_safe_directories_empty(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stderr="no such key")
        result = client.get_safe_directories(Path("/repo"))
        assert result == []


class TestGitCliClientEdge:
    """Edge case tests for GitCliClient."""

    @pytest.fixture
    def client(self):
        return GitCliClient()

    @patch("subprocess.run")
    def test_rev_parse_multiple_args(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="v1.0.0\n")
        result = client.rev_parse(["--short", "HEAD~1"], Path("/repo"))
        assert result == "v1.0.0"

    @patch("subprocess.run")
    def test_diff_name_only_right_none(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="changed.py\n"
        )
        result = client.diff_name_only("HEAD", None, Path("/repo"))
        call_args = mock_run.call_args.args[0]
        assert "HEAD" in call_args
        assert "diff" in call_args

    @patch("subprocess.run")
    def test_ls_remote_with_ref_filter(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\trefs/heads/main\n")
        result = client.ls_remote("origin", "refs/heads/main", Path("/repo"))
        call_args = mock_run.call_args.args[0]
        assert "refs/heads/main" in call_args


class TestBackwardCompatFunctions:
    """Tests for backward-compatible module functions."""

    @patch("subprocess.run")
    def test_resolve_repo_root_function(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")
        result = resolve_repo_root(Path("/test"))
        assert result == Path("/test/repo")

    @patch("subprocess.run")
    def test_is_inside_work_tree_function(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        result = is_inside_work_tree(Path("/test"))
        assert result is True

    @patch("subprocess.run")
    def test_get_origin_remote_function(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="git@github.com:user/repo.git\n")
        result = get_origin_remote(Path("/test"))
        assert result == "git@github.com:user/repo.git"

    @patch("subprocess.run")
    def test_status_porcelain_function(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="M  file.py\n")
        result = status_porcelain(Path("/test"))
        assert "M  file.py" in result


class TestGitCliClientIntegration:
    """Integration tests - require real git installation."""

    def test_resolve_repo_root_in_real_repo(self):
        """Test with the actual test repository."""
        client = GitCliClient()
        # This test runs in the ai_files repo
        result = client.resolve_repo_root()
        assert result is not None
        assert result.exists()

    def test_is_inside_work_tree_in_real_repo(self):
        """Test with the actual test repository."""
        client = GitCliClient()
        result = client.is_inside_work_tree(Path("/Users/koeppben/work/ai_files"))
        assert result is True

    def test_status_porcelain_real_repo(self):
        """Test status in real repo."""
        client = GitCliClient()
        result = client.status_porcelain(Path("/Users/koeppben/work/ai_files"))
        assert isinstance(result, list)
