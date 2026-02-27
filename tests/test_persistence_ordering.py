from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _init_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture(autouse=True)
def _binding_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    workspaces_home = cfg / "workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": "python3",
        },
    }
    (commands_home / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[1]
    (commands_home / "phase_api.yaml").write_text((repo_root / "phase_api.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def test_phase_router_blocks_phase_2_1_without_persistence_committed() -> None:
    from governance.application.use_cases.phase_router import route_phase

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
    assert routed.phase == "1.1-Bootstrap"
    assert routed.workspace_ready is False


def test_phase_router_allows_phase_2_1_with_persistence_committed() -> None:
    from governance.application.use_cases.phase_router import route_phase

    session_state_document = {
        "SESSION_STATE": {
            "phase": "2",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
            "RulebookLoadEvidence": {"core": "${COMMANDS_HOME}/master.md"},
            "AddonsEvidence": {},
            "RepoDiscovery": {"Completed": True, "RepoCacheFile": "cache", "RepoMapDigestFile": "digest"},
            "phase_transition_evidence": True,
        }
    }
    routed = route_phase(
        requested_phase="2.1",
        requested_active_gate="Decision Pack",
        requested_next_gate_condition="Execute Phase 2.1",
        session_state_document=session_state_document,
        repo_is_git_root=True,
    )
    assert routed.phase in {"2.1", "1.5-BusinessRules", "3A-API-Inventory"}
    assert routed.workspace_ready is True


def test_session_state_template_includes_persistence_fields() -> None:
    from governance.entrypoints.bootstrap_session_state import session_state_template

    template = session_state_template("a1b2c3d4e5f6a1b2c3d4e5f6", "test-repo")
    session = template.get("SESSION_STATE", {})

    assert session.get("RepoFingerprint") == "a1b2c3d4e5f6a1b2c3d4e5f6"
    # Template starts with PersistenceCommitted=False (set to True only after successful pointer write + verify)
    assert session.get("PersistenceCommitted") is False
    assert session.get("WorkspaceReadyGateCommitted") is False
    assert session.get("phase_transition_evidence") is False
    # BusinessRules starts as pending (not pre-resolved to not-applicable)
    scope = session.get("Scope", {})
    assert scope.get("BusinessRules") == "pending"
    gates = session.get("Gates", {})
    assert gates.get("P5.4-BusinessRules") == "pending"


def test_bootstrap_persistence_hook_blocked_when_writes_not_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)

    import importlib
    mod = importlib.import_module("governance.entrypoints.bootstrap_persistence_hook")
    importlib.reload(mod)

    result = mod.run_persistence_hook(repo_root=tmp_path)

    assert result.get("workspacePersistenceHook") == "blocked"
    assert result.get("reason_code") == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert result.get("writes_allowed") is False
    assert str(result.get("log_path", "")).endswith("error.log.jsonl")
