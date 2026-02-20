from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "diagnostics" / "start_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("start_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_readonly module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module_with_env(env: dict[str, str]):
    script = REPO_ROOT / "diagnostics" / "start_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("start_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_readonly module")
    
    old_env = dict(os.environ)
    try:
        os.environ.update(env)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.mark.governance
def test_start_preflight_readonly_module_exists_and_declares_readonly():
    module = _load_module()
    assert module.READ_ONLY is True


@pytest.mark.governance
def test_start_preflight_readonly_hook_never_persists(capsys: pytest.CaptureFixture[str]):
    module = _load_module()
    module.run_persistence_hook()
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "skipped"
    assert payload["reason"] == "read-only-preflight"
    assert payload["read_only"] is True


@pytest.mark.governance
def test_start_preflight_derive_repo_fingerprint_requires_git_repo(tmp_path: Path):
    module = _load_module()
    assert module.derive_repo_fingerprint(tmp_path) is None


@pytest.mark.governance
def test_start_preflight_derive_repo_fingerprint_from_git_repo(tmp_path: Path):
    module = _load_module()
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, text=True)
    fp = module.derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str) and len(fp) == 24


@pytest.mark.governance
def test_start_md_uses_readonly_preflight_helper():
    text = (REPO_ROOT / "start.md").read_text(encoding="utf-8")
    assert "start_preflight_readonly.py" in text
    assert "start_preflight_persistence.py" not in text


@pytest.mark.governance
def test_start_persistence_store_module_removed():
    assert not (REPO_ROOT / "governance" / "infrastructure" / "start_persistence_store.py").exists()


@pytest.mark.governance
def test_start_preflight_readonly_respects_write_env():
    module = _load_module_with_env({"OPENCODE_DIAGNOSTICS_ALLOW_WRITE": "1", "CI": ""})
    assert module.READ_ONLY is False


@pytest.mark.governance
def test_start_preflight_readonly_is_true_in_ci():
    module = _load_module_with_env({"CI": "true"})
    assert module.READ_ONLY is True


@pytest.mark.governance
def test_start_preflight_readonly_is_true_by_default():
    module = _load_module_with_env({})
    assert module.READ_ONLY is True


@pytest.mark.governance
def test_run_persistence_hook_returns_skipped_when_read_only(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({})
    result = module.run_persistence_hook()
    
    assert result["workspacePersistenceHook"] == "skipped"
    assert result["reason"] == "read-only-preflight"
    assert result["read_only"] is True


@pytest.mark.governance
def test_run_persistence_hook_delegates_to_hook_module_when_write_enabled(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"OPENCODE_DIAGNOSTICS_ALLOW_WRITE": "1", "CI": ""})
    
    mock_hook_result = {
        "workspacePersistenceHook": "ok",
        "reason": "bootstrap-completed",
        "repo_fingerprint": "testfingerprint123456",
        "read_only": False,
    }
    
    with patch.dict(
        "sys.modules",
        {"diagnostics.start_persistence_hook": MagicMock(run_persistence_hook=MagicMock(return_value=mock_hook_result))}
    ):
        result = module.run_persistence_hook()
    
    assert result["workspacePersistenceHook"] == "ok"
    assert result["repo_fingerprint"] == "testfingerprint123456"


@pytest.mark.governance
def test_run_persistence_hook_propagates_hook_failure(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"OPENCODE_DIAGNOSTICS_ALLOW_WRITE": "1", "CI": ""})
    
    mock_hook_result = {
        "workspacePersistenceHook": "failed",
        "reason": "repo-fingerprint-derivation-failed",
        "read_only": False,
    }
    
    with patch.dict(
        "sys.modules",
        {"diagnostics.start_persistence_hook": MagicMock(run_persistence_hook=MagicMock(return_value=mock_hook_result))}
    ):
        result = module.run_persistence_hook()
    
    assert result["workspacePersistenceHook"] == "failed"
    assert result["reason"] == "repo-fingerprint-derivation-failed"
