from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from governance.application.use_cases.phase_router import route_phase


def _set_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))


def _write_governance_paths_json(*, home: Path, commands_home: Path, workspaces_home: Path) -> None:
    config_root = home / ".config" / "opencode"
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "configRoot": str(config_root),
            "pythonCommand": sys.executable,
        },
        "commandProfiles": {},
    }
    evidence_dir = config_root / "commands"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (repo_root / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init"],
                   cwd=str(repo_root), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.mark.governance
def test_start_persistence_hook_commits_fingerprint_and_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    _set_home(monkeypatch, home)

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", raising=False)

    repo_root = tmp_path / "repo"
    _init_git_repo(repo_root)

    workspaces_home = tmp_path / "workspaces"
    _write_governance_paths_json(home=home, commands_home=Path(__file__).resolve().parents[1], workspaces_home=workspaces_home)

    import importlib
    import diagnostics.start_persistence_hook as hook
    importlib.reload(hook)

    with patch.object(hook, "COMMANDS_HOME", Path(__file__).resolve().parents[1]):
        with patch.object(hook, "derive_repo_fingerprint", return_value="a1b2c3d4e5f6a1b2c3d4e5f6"):
            with patch.object(hook, "_verify_pointer_exists", return_value=(True, "ok")):
                with patch.object(hook, "_verify_workspace_session_exists", return_value=(True, "ok")):
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""

                    with patch.object(hook.subprocess, "run", return_value=mock_result):
                        result = hook.run_persistence_hook(repo_root=repo_root)

    assert str(result.get("workspacePersistenceHook") or "").lower() == "ok"
    fp = str(result.get("repo_fingerprint") or "").strip()
    assert fp


@pytest.mark.governance
def test_start_identity_blocks_when_git_is_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    monkeypatch.setenv("OPENCODE_DISABLE_GIT", "1")

    from governance.application.use_cases.start_bootstrap import evaluate_start_identity
    from governance.engine.adapters import LocalHostAdapter
    from governance.infrastructure.wiring import configure_gateway_registry

    configure_gateway_registry()
    adapter = LocalHostAdapter()
    res = evaluate_start_identity(adapter=adapter)
    assert res.workspace_ready is False
    assert res.repo_fingerprint == ""


@pytest.mark.governance
def test_phase_2_1_routing_blocks_without_persistence_committed() -> None:
    session_state_document = {
        "SESSION_STATE": {
            "phase": "1.1-Bootstrap",
            "WorkspaceReadyGateCommitted": True,
        }
    }
    routed = route_phase(
        requested_phase="2.1",
        requested_active_gate="x",
        requested_next_gate_condition="y",
        session_state_document=session_state_document,
        repo_is_git_root=True,
    )
    assert routed.workspace_ready is False
