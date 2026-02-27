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
    script = REPO_ROOT / "governance" / "entrypoints" / "bootstrap_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("bootstrap_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load bootstrap_preflight_readonly module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module_with_env(env: dict[str, str]):
    script = REPO_ROOT / "governance" / "entrypoints" / "bootstrap_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("bootstrap_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load bootstrap_preflight_readonly module")
    
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
def test_bootstrap_preflight_readonly_module_imports_ssot_writes_allowed():
    """bootstrap_preflight_readonly uses SSOT write_policy.writes_allowed()."""
    module = _load_module()
    assert hasattr(module, "writes_allowed")
    assert callable(module.writes_allowed)


@pytest.mark.governance
def test_bootstrap_preflight_readonly_hook_blocks_when_writes_not_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)
    import importlib
    import governance.entrypoints.bootstrap_preflight_readonly as mod
    importlib.reload(mod)
    
    try:
        mod.run_persistence_hook()
    except SystemExit as e:
        assert e.code == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"


@pytest.mark.governance
def test_bootstrap_preflight_derive_repo_fingerprint_requires_git_repo(tmp_path: Path):
    module = _load_module()
    assert module.derive_repo_fingerprint(tmp_path) is None


@pytest.mark.governance
def test_bootstrap_preflight_derive_repo_fingerprint_from_git_repo(tmp_path: Path):
    module = _load_module()
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True, text=True)
    fp = module.derive_repo_fingerprint(tmp_path)
    assert isinstance(fp, str) and len(fp) == 24


@pytest.mark.governance
def test_bootstrap_md_uses_readonly_preflight_helper():
    text = (REPO_ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
    assert "bootstrap_preflight_readonly.py" not in text
    assert "bootstrap_preflight_persistence.py" not in text


@pytest.mark.governance
def test_bootstrap_persistence_store_module_removed():
    assert not (REPO_ROOT / "governance" / "infrastructure" / "bootstrap_persistence_store.py").exists()


@pytest.mark.governance
def test_bootstrap_preflight_writes_allowed_true_by_default():
    """SSOT: writes_allowed() is True by default."""
    module = _load_module_with_env({"CI": ""})
    assert module.writes_allowed() is True


@pytest.mark.governance
def test_bootstrap_preflight_writes_allowed_true_in_ci():
    """SSOT: writes_allowed() is True in CI (unless FORCE_READ_ONLY=1)."""
    module = _load_module_with_env({"CI": "true"})
    assert module.writes_allowed() is True


@pytest.mark.governance
def test_bootstrap_preflight_writes_allowed_false_when_force_read_only(monkeypatch: pytest.MonkeyPatch):
    """SSOT: writes_allowed() is False when FORCE_READ_ONLY=1."""
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    import importlib
    import governance.entrypoints.write_policy as wp
    importlib.reload(wp)
    assert wp.writes_allowed() is False


@pytest.mark.governance
def test_run_persistence_hook_blocks_when_writes_not_allowed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)
    import importlib
    import governance.entrypoints.bootstrap_preflight_readonly as mod
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

    repo_root = REPO_ROOT
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        {
            "workspacePersistenceHook": "ok",
            "reason": "bootstrap-completed",
            "repo_fingerprint": "testfingerprint123456",
            "writes_allowed": True,
        }
    )
    mock_proc.stderr = ""

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(repo_root, "git", {"ok": True})):
        with patch.object(module.subprocess, "run", return_value=mock_proc) as mock_run:
            result = module.run_persistence_hook()

    assert result["workspacePersistenceHook"] == "ok"
    assert result["repo_fingerprint"] == "testfingerprint123456"
    assert result["bootstrap_hook_command"] == f"{module.sys.executable} -m governance.entrypoints.bootstrap_persistence_hook"
    assert result["cwd"]
    assert result["repo_root_detected"] == str(repo_root)
    run_args = mock_run.call_args.args[0]
    assert run_args[:3] == [module.sys.executable, "-m", "governance.entrypoints.bootstrap_persistence_hook"]
    call_args = mock_run.call_args.kwargs
    assert call_args["cwd"] == str(repo_root)
    expected_prefix = str(repo_root) + module.os.pathsep + str(module.COMMANDS_HOME)
    assert str(call_args["env"].get("PYTHONPATH", "")).startswith(expected_prefix)


@pytest.mark.governance
def test_run_persistence_hook_exits_on_hook_failure(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "ModuleNotFoundError: No module named governance"

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(REPO_ROOT, "git", {"ok": True})):
        with patch.object(module.subprocess, "run", return_value=mock_proc):
            try:
                module.run_persistence_hook()
            except SystemExit as e:
                assert e.code == 2

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert payload["hook_invoked"] is True
    assert payload["failure_stage"] in {"subprocess", "parse", "hook-payload", "hook_payload"}
    assert payload.get("stderr_snippet")
    assert payload.get("log_path")


@pytest.mark.governance
def test_run_persistence_hook_blocks_when_repo_root_not_detectable(capsys: pytest.CaptureFixture[str]):
    module = _load_module_with_env({"CI": ""})

    with patch.object(module, "_resolve_repo_root_for_hook", return_value=(None, "git-miss", {"ok": False})):
        try:
            module.run_persistence_hook()
        except SystemExit as exc:
            assert exc.code == 2

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["workspacePersistenceHook"] == "blocked"
    assert payload["reason_code"] == "BLOCKED-REPO-ROOT-NOT-DETECTABLE"
    assert payload["hook_invoked"] is False
    assert payload["failure_stage"] == "repo_root"
    assert payload["bootstrap_hook_command"].endswith("-m governance.entrypoints.bootstrap_persistence_hook")
    assert payload["python_executable"]


@pytest.mark.governance
def test_resolve_repo_root_for_hook_prefers_env_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module_with_env({"CI": ""})
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(outside)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(repo_root))

    resolved, source, probe = module._resolve_repo_root_for_hook()

    assert resolved == repo_root
    assert source == "env"
    assert probe.get("ok") is True
