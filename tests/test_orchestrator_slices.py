from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _load_orchestrator_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "governance_runtime"
        / "entrypoints"
        / "persist_workspace_artifacts_orchestrator.py"
    )
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_validate_path_constraints_blocks_config_inside_repo(tmp_path: Path):
    module = _load_orchestrator_module()
    repo_root = tmp_path / "repo"
    config_root = repo_root / ".config" / "opencode"
    (repo_root / ".git").mkdir(parents=True)
    config_root.mkdir(parents=True)

    with patch.object(module, "emit_gate_failure") as mock_gate:
        ok = module._validate_path_constraints(
            config_root=config_root,
            repo_root=repo_root,
            python_cmd="python3",
            quiet=True,
        )

    assert ok is False
    assert mock_gate.called
    assert mock_gate.call_args.kwargs["code"] == "CONFIG_ROOT_INSIDE_REPO"


@pytest.mark.governance
def test_prepare_workspace_returns_lock_timeout_exit(tmp_path: Path):
    module = _load_orchestrator_module()
    workspaces_home = tmp_path / "cfg" / "workspaces"
    workspaces_home.mkdir(parents=True)

    args = SimpleNamespace(
        no_session_update=True,
        repo_name="repo",
        dry_run=False,
        skip_lock=False,
        quiet=True,
    )

    with patch.object(module, "acquire_workspace_lock", side_effect=TimeoutError):
        with patch.object(module, "emit_gate_failure") as mock_gate:
            prepared, exit_code = module._prepare_workspace(
                binding_paths={"workspacesHome": str(workspaces_home)},
                repo_fingerprint="a1b2c3d4e5f6a1b2c3d4e5f6",
                config_root=tmp_path / "cfg",
                repo_root=tmp_path / "repo",
                python_cmd="python3",
                args=args,
                read_only=False,
            )

    assert prepared is None
    assert exit_code == 2
    assert mock_gate.called
    assert mock_gate.call_args.kwargs["code"] == "WORKSPACE_LOCK_TIMEOUT"


@pytest.mark.governance
def test_prepare_workspace_returns_bootstrap_failure_exit(tmp_path: Path):
    module = _load_orchestrator_module()
    config_root = tmp_path / "cfg"
    workspaces_home = config_root / "workspaces"
    repo_root = tmp_path / "repo"
    config_root.mkdir(parents=True)
    workspaces_home.mkdir(parents=True)
    repo_root.mkdir(parents=True)

    args = SimpleNamespace(
        no_session_update=False,
        repo_name="repo",
        dry_run=False,
        skip_lock=True,
        quiet=True,
    )

    with patch.object(module, "_bootstrap_missing_session_state", return_value=(False, "failed")):
        prepared, exit_code = module._prepare_workspace(
            binding_paths={"workspacesHome": str(workspaces_home)},
            repo_fingerprint="a1b2c3d4e5f6a1b2c3d4e5f6",
            config_root=config_root,
            repo_root=repo_root,
            python_cmd="python3",
            args=args,
            read_only=False,
        )

    assert prepared is None
    assert exit_code == 2
