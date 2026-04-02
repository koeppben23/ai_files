from __future__ import annotations

import subprocess
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from governance_runtime.application.ports.process_runner import (
    ProcessResult,
    ProcessRunnerPort,
)
from governance_runtime.infrastructure.adapters.process.subprocess_runner import SubprocessRunner


class TestProcessResult:
    """Tests for ProcessResult dataclass."""

    def test_process_result_creation(self):
        result = ProcessResult(returncode=0, stdout="hello", stderr="")
        assert result.returncode == 0
        assert result.stdout == "hello"
        assert result.stderr == ""

    def test_process_result_immutable(self):
        result = ProcessResult(returncode=0, stdout="hello", stderr="")
        with pytest.raises(AttributeError):
            result.returncode = 1


class TestProcessRunnerPortHappy:
    """Happy path tests for ProcessRunnerPort."""

    @pytest.fixture
    def runner(self):
        return SubprocessRunner()

    @patch("subprocess.run")
    def test_run_simple_command(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="output", stderr=""
        )
        result = runner.run(["echo", "hello"])
        assert result.returncode == 0
        assert result.stdout == "output"

    @patch("subprocess.run")
    def test_run_with_cwd(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(["ls"], cwd=Path("/tmp"))
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("cwd") == "/tmp"

    @patch("subprocess.run")
    def test_run_with_env_merged(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(["env"], env={"MY_VAR": "value"})
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        # env should be a dict that includes both os.environ and MY_VAR
        passed_env = call_kwargs.get("env")
        assert passed_env is not None
        assert "MY_VAR" in passed_env
        assert passed_env["MY_VAR"] == "value"
        # Should also include typical env vars from os.environ
        assert "PATH" in passed_env or "Path" in passed_env

    @patch("subprocess.run")
    def test_run_with_timeout(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(["sleep", "1"], timeout_seconds=5)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("timeout") == 5

    @patch("subprocess.run")
    def test_run_check_false_by_default(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        result = runner.run(["false"])
        assert result.returncode == 1

    @patch("subprocess.run")
    def test_run_captures_stderr(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr="error output"
        )
        result = runner.run(["cmd"])
        assert result.stderr == "error output"


class TestProcessRunnerPortBad:
    """Bad path tests for ProcessRunnerPort."""

    @pytest.fixture
    def runner(self):
        return SubprocessRunner()

    @patch("subprocess.run")
    def test_run_check_raises_on_nonzero(self, mock_run, runner):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error"
        )
        # check=True should cause subprocess.run to raise CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["false"], "", "error"
        )
        with pytest.raises(subprocess.CalledProcessError):
            runner.run(["false"], check=True)

    @patch("subprocess.run")
    def test_run_timeout_expired(self, mock_run, runner):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)
        with pytest.raises(subprocess.TimeoutExpired):
            runner.run(["sleep", "100"], timeout_seconds=0.001)

    @patch("subprocess.run")
    def test_run_empty_argv(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run([])
        assert result.returncode == 0


class TestProcessRunnerPortCorner:
    """Corner case tests for ProcessRunnerPort."""

    @pytest.fixture
    def runner(self):
        return SubprocessRunner()

    @patch("subprocess.run")
    def test_run_none_cwd(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(["pwd"], cwd=None)
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("cwd") is None

    @patch("subprocess.run")
    def test_run_none_env_uses_current(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(["env"], env=None)
        call_kwargs = mock_run.call_args.kwargs
        # When env=None, subprocess uses current environment
        assert "env" not in call_kwargs or call_kwargs["env"] is None

    @patch("subprocess.run")
    def test_run_with_special_chars_in_argv(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(["echo", "hello world with 'special' chars"])
        assert result.returncode == 0


class TestProcessRunnerPortEdge:
    """Edge case tests for ProcessRunnerPort."""

    @pytest.fixture
    def runner(self):
        return SubprocessRunner()

    @patch("subprocess.run")
    def test_run_with_zero_timeout_treated_as_no_timeout(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        # Zero timeout should be treated as no timeout (None)
        result = runner.run(["echo", "test"], timeout_seconds=0)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("timeout") is None

    @patch("subprocess.run")
    def test_run_with_negative_timeout_treated_as_no_timeout(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        # Negative timeout should be treated as no timeout (None)
        result = runner.run(["echo", "test"], timeout_seconds=-1)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("timeout") is None

    @patch("subprocess.run")
    def test_run_with_tuple_argv(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.run(("echo", "test"))
        assert result.returncode == 0


class TestSubprocessRunnerIntegration:
    """Integration tests for SubprocessRunner."""

    def test_run_echo_command(self):
        runner = SubprocessRunner()
        result = runner.run(["echo", "hello"])
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_run_nonexistent_command(self):
        runner = SubprocessRunner()
        # On macOS, trying to run a nonexistent command raises FileNotFoundError
        # This is different from returning a non-zero exit code
        with pytest.raises(FileNotFoundError):
            runner.run(["nonexistent_command_12345"])

    def test_run_with_cwd_current(self):
        runner = SubprocessRunner()
        result = runner.run(["pwd"], cwd=Path.cwd())
        assert result.returncode == 0
