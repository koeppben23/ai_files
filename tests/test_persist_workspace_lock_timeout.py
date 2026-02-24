from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.governance
def test_persist_workspace_lock_timeout_emits_gate_failure(tmp_path: Path):
    script = Path(__file__).resolve().parents[1] / "diagnostics" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cfg = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    workspaces = cfg / "workspaces"
    cfg.mkdir(parents=True)
    repo_root.mkdir(parents=True)
    workspaces.mkdir(parents=True)

    args = SimpleNamespace(
        repo_fingerprint="a1b2c3d4e5f6a1b2c3d4e5f6",
        repo_root=repo_root,
        repo_name="repo",
        config_root=cfg,
        force=False,
        dry_run=False,
        no_session_update=True,
        quiet=True,
        skip_lock=False,
        require_phase2=False,
    )

    with patch.object(module, "parse_args", return_value=args):
        with patch.object(
            module,
            "resolve_binding_config",
            return_value=(cfg, {"workspacesHome": str(workspaces), "pythonCommand": "python3"}, cfg / "commands" / "governance.paths.json"),
        ):
            with patch.object(module, "_resolve_repo_fingerprint", return_value=(args.repo_fingerprint, "arg", "explicit")):
                with patch.object(module, "_read_only", return_value=False):
                    with patch.object(module, "acquire_workspace_lock", side_effect=TimeoutError):
                        with patch.object(module, "emit_gate_failure") as mock_gate:
                            code = module.main()

    assert code == 2
    assert mock_gate.called
    assert mock_gate.call_args.kwargs["code"] == "WORKSPACE_LOCK_TIMEOUT"
