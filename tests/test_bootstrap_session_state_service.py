from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util

import pytest


@pytest.mark.governance
def test_bootstrap_service_lock_timeout_emits_gate_failure(tmp_path: Path):
    script = Path(__file__).resolve().parents[1] / "governance" / "entrypoints" / "bootstrap_session_state_orchestrator.py"
    spec = importlib.util.spec_from_file_location("bootstrap_session_state_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config_root = tmp_path / "cfg"
    repo_root = tmp_path / "repo"
    config_root.mkdir(parents=True)
    repo_root.mkdir(parents=True)

    args = SimpleNamespace(
        repo_fingerprint="a1b2c3d4e5f6a1b2c3d4e5f6",
        repo_root=repo_root,
        repo_name="repo",
        config_root=config_root,
        force=False,
        dry_run=False,
        skip_artifact_backfill=False,
        no_commit=False,
    )

    with patch.object(module, "parse_args", return_value=args):
        with patch.object(
            module,
            "resolve_binding_config",
            return_value=(config_root, {"workspacesHome": str(config_root / "workspaces")}, config_root / "commands" / "governance.paths.json"),
        ):
            with patch.object(module, "resolve_repo_root_ssot", return_value=(repo_root, "explicit")):
                with patch.object(module, "_validate_repo_fingerprint", return_value=args.repo_fingerprint):
                    with patch.object(module, "_writes_allowed", return_value=True):
                        with patch.object(module, "acquire_workspace_lock", side_effect=TimeoutError):
                            with patch.object(module, "emit_gate_failure") as mock_gate:
                                code = module.main()

    assert code == 6
    assert mock_gate.called
    assert mock_gate.call_args.kwargs["code"] == "WORKSPACE_LOCK_TIMEOUT"
