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
    from diagnostics.bootstrap_session_state import session_state_template

    template = session_state_template("test-fingerprint-123", "test-repo")
    session = template.get("SESSION_STATE", {})

    assert session.get("RepoFingerprint") == "test-fingerprint-123"
    assert session.get("PersistenceCommitted") is True
    assert session.get("WorkspaceReadyGateCommitted") is True
    assert session.get("phase_transition_evidence") is True


def test_start_persistence_hook_blocked_when_writes_not_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "1")
    monkeypatch.delenv("CI", raising=False)

    import importlib
    mod = importlib.import_module("diagnostics.start_persistence_hook")
    importlib.reload(mod)

    result = mod.run_persistence_hook(repo_root=tmp_path)

    assert result.get("workspacePersistenceHook") == "blocked"
    assert result.get("reason_code") == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert result.get("writes_allowed") is False
