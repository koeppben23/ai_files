from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, run, write_governance_paths


@pytest.mark.governance
def test_persist_workspace_artifacts_bootstraps_missing_session_state(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_fp = "autobootstrap-112233"
    write_governance_paths(cfg)

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            repo_fp,
            "--config-root",
            str(cfg),
            "--quiet",
        ]
    )
    assert result.returncode == 0, f"persist helper failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"

    payload = json.loads(result.stdout)
    assert payload.get("workspacePersistenceHook") == "skipped"
    assert payload.get("read_only") is True

    session_file = cfg / "workspaces" / repo_fp / "SESSION_STATE.json"
    assert not session_file.exists(), "read-only diagnostics must not create repo-scoped SESSION_STATE.json"


@pytest.mark.governance
def test_persist_workspace_artifacts_does_not_bootstrap_when_session_updates_disabled(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_fp = "autobootstrap-445566"
    write_governance_paths(cfg)

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            repo_fp,
            "--config-root",
            str(cfg),
            "--no-session-update",
            "--quiet",
        ]
    )
    assert result.returncode == 0, f"persist helper failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"

    payload = json.loads(result.stdout)
    assert payload.get("workspacePersistenceHook") == "skipped"
    assert payload.get("read_only") is True

    session_file = cfg / "workspaces" / repo_fp / "SESSION_STATE.json"
    assert not session_file.exists(), "session file should not be created when --no-session-update is set"
