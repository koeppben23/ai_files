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
def test_start_preflight_readonly_module_exists_and_declares_writes_allowed():
    module = _load_module()
    assert callable(module._writes_allowed)
    assert module._writes_allowed(mode="user") is True


@pytest.mark.governance
def test_start_preflight_readonly_hook_blocks_when_writes_not_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)
    import importlib
    import diagnostics.start_preflight_readonly as mod
    importlib.reload(mod)
    
    try:
        mod.run_persistence_hook()
    except SystemExit as e:
        assert e.code == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"


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
def test_start_preflight_writes_allowed_true_by_default():
    module = _load_module_with_env({"CI": ""})
    assert module._writes_allowed(mode="user") is True


@pytest.mark.governance
def test_start_preflight_writes_allowed_true_in_ci():
    module = _load_module_with_env({"CI": "true"})
    assert module._writes_allowed(mode="pipeline") is True


@pytest.mark.governance
def test_start_preflight_writes_allowed_false_when_force_read_only(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "1")
    import importlib
    import diagnostics.start_preflight_readonly as mod
    importlib.reload(mod)
    assert mod._writes_allowed(mode="user") is False


@pytest.mark.governance
def test_run_persistence_hook_blocks_when_writes_not_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)
    import importlib
    import diagnostics.start_preflight_readonly as mod
    importlib.reload(mod)
    
    try:
        mod.run_persistence_hook()
    except SystemExit as e:
        assert e.code == 2
    
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"


@pytest.mark.governance
def test_run_persistence_hook_delegates_to_hook_module(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})
    
    mock_hook_result = {
        "workspacePersistenceHook": "ok",
        "reason": "bootstrap-completed",
        "repo_fingerprint": "testfingerprint123456",
        "writes_allowed": True,
    }
    
    with patch.dict(
        "sys.modules",
        {"diagnostics.start_persistence_hook": MagicMock(run_persistence_hook=MagicMock(return_value=mock_hook_result))}
    ):
        result = module.run_persistence_hook()
    
    assert result["workspacePersistenceHook"] == "ok"
    assert result["repo_fingerprint"] == "testfingerprint123456"


@pytest.mark.governance
def test_run_persistence_hook_exits_on_hook_failure(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})
    
    mock_hook_result = {
        "workspacePersistenceHook": "failed",
        "reason": "repo-fingerprint-derivation-failed",
        "writes_allowed": True,
    }
    
    with patch.dict(
        "sys.modules",
        {"diagnostics.start_persistence_hook": MagicMock(run_persistence_hook=MagicMock(return_value=mock_hook_result))}
    ):
        try:
            module.run_persistence_hook()
        except SystemExit as e:
            assert e.code == 2
    
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "failed"
    assert payload["reason"] == "repo-fingerprint-derivation-failed"
