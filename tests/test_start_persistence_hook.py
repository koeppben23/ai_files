"""Tests for diagnostics/start_persistence_hook.py - GOOD/BAD/EDGE paths."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.util import REPO_ROOT


def _load_hook_module_with_env(env: dict[str, str]):
    script = REPO_ROOT / "diagnostics" / "start_persistence_hook.py"
    spec = importlib.util.spec_from_file_location("start_persistence_hook", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_persistence_hook module")
    
    old_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(env)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(old_env)


class TestEnvironmentHandling:
    """Tests for _writes_allowed environment variable handling."""

    @pytest.mark.governance
    def test_writes_allowed_true_by_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", raising=False)
        from diagnostics.start_persistence_hook import _writes_allowed
        assert _writes_allowed() is True

    @pytest.mark.governance
    def test_writes_allowed_false_when_force_read_only_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "1")
        import importlib
        import diagnostics.start_persistence_hook as mod
        importlib.reload(mod)
        assert mod._writes_allowed() is False

    @pytest.mark.governance
    def test_writes_allowed_true_when_ci_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", raising=False)
        from diagnostics.start_persistence_hook import _writes_allowed
        assert _writes_allowed() is True

    @pytest.mark.governance
    def test_writes_allowed_ignores_allow_write_flag(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("OPENCODE_DIAGNOSTICS_ALLOW_WRITE", "1")
        monkeypatch.delenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", raising=False)
        from diagnostics.start_persistence_hook import _writes_allowed
        assert _writes_allowed() is True


class TestPersistenceHookGoodPaths:
    """Tests for successful persistence scenarios."""

    @pytest.mark.governance
    def test_returns_blocked_when_writes_not_allowed(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        with patch.object(module, "_writes_allowed", return_value=False):
            result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "blocked"
        assert result["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"
        assert result["writes_allowed"] is False

    @pytest.mark.governance
    def test_calls_bootstrap_by_default(self, tmp_path: Path):
        module = _load_hook_module_with_env({
            "CI": "",
        })
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Bootstrap completed"
        mock_result.stderr = ""
        
        # Mock all external dependencies
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error"):
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    # Create fake bootstrap script
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result) as mock_run:
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "ok"
        assert result["reason"] == "bootstrap-completed"
        assert result["repo_fingerprint"] == "testfingerprint123456"
        
        call_args = mock_run.call_args
        assert "bootstrap_session_state.py" in str(call_args[0][0])

    @pytest.mark.governance
    def test_passes_repo_name_to_bootstrap(self, tmp_path: Path):
        module = _load_hook_module_with_env({
            "CI": "",
        })
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error"):
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result) as mock_run:
                        module.run_persistence_hook(repo_root=tmp_path)
        
        cmd = mock_run.call_args[0][0]
        assert "--repo-name" in cmd
        repo_name_idx = cmd.index("--repo-name") + 1
        assert cmd[repo_name_idx] == tmp_path.name


class TestPersistenceHookBadPaths:
    """Tests for error scenarios."""

    @pytest.mark.governance
    def test_fails_when_fingerprint_missing(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        with patch.object(module, "derive_repo_fingerprint", return_value=None):
            with patch.object(module, "safe_log_error") as mock_log:
                result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert result["reason"] == "repo-fingerprint-derivation-failed"
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["reason_key"] == "ERR-PERSISTENCE-FINGERPRINT-DERIVATION-FAILED"

    @pytest.mark.governance
    def test_fails_when_bootstrap_script_missing(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        # Use empty tmp_path as COMMANDS_HOME (no bootstrap script exists)
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error") as mock_log:
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert result["reason"] == "bootstrap-script-not-found"
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["reason_key"] == "ERR-PERSISTENCE-BOOTSTRAP-SCRIPT-MISSING"

    @pytest.mark.governance
    def test_fails_when_bootstrap_returns_nonzero(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: something went wrong"
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error") as mock_log:
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result):
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert result["reason"] == "bootstrap-returncode-nonzero"
        assert result["returncode"] == 1
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["reason_key"] == "ERR-PERSISTENCE-BOOTSTRAP-NONZERO-EXIT"

    @pytest.mark.governance
    def test_fails_when_bootstrap_raises_exception(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error") as mock_log:
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", side_effect=RuntimeError("boom")):
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert result["reason"] == "bootstrap-exception"
        assert "boom" in str(result["error"])
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["reason_key"] == "ERR-PERSISTENCE-BOOTSTRAP-EXCEPTION"


class TestPersistenceHookEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.governance
    def test_truncates_long_stdout_on_failure(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        long_output = "x" * 1000
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = long_output
        mock_result.stderr = ""
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error"):
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result):
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert len(result["stdout"]) <= 500

    @pytest.mark.governance
    def test_truncates_long_stderr_on_failure(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        long_output = "y" * 1000
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = long_output
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error"):
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result):
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert len(result["stderr"]) <= 500

    @pytest.mark.governance
    def test_handles_empty_stdout_stderr(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = None
        mock_result.stderr = None
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error"):
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result):
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert result["stdout"] == ""
        assert result["stderr"] == ""

    @pytest.mark.governance
    def test_handles_whitespace_only_output(self, tmp_path: Path):
        module = _load_hook_module_with_env({"CI": ""})
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "   \n\t  "
        mock_result.stderr = "  \n  "
        
        with patch.object(module, "derive_repo_fingerprint", return_value="testfingerprint123456"):
            with patch.object(module, "safe_log_error"):
                with patch.object(module, "COMMANDS_HOME", tmp_path):
                    bootstrap_script = tmp_path / "diagnostics" / "bootstrap_session_state.py"
                    bootstrap_script.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_script.write_text("# fake")
                    
                    with patch.object(module.subprocess, "run", return_value=mock_result):
                        result = module.run_persistence_hook(repo_root=tmp_path)
        
        assert result["workspacePersistenceHook"] == "failed"
        assert result["stdout"] == ""
        assert result["stderr"] == ""
