from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, run, write_governance_paths


@pytest.mark.governance
def test_persist_workspace_artifacts_blocks_config_root_inside_repo(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()
    bad_config_root = repo_root / "C"
    write_governance_paths(bad_config_root)

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo_root),
            "--config-root",
            str(bad_config_root),
            "--quiet",
        ],
        cwd=repo_root,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload.get("status") == "blocked"
    assert payload.get("reason_code") == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert "outside" in str(payload.get("required_operator_action", "")).lower()
    assert not (repo_root / "business-rules.md").exists()
    assert not (repo_root / "SESSION_STATE.json").exists()


@pytest.mark.governance
def test_bootstrap_session_state_blocks_config_root_inside_repo(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "bootstrap_session_state.py"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()
    bad_config_root = repo_root / "C"
    write_governance_paths(bad_config_root)

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            "88b39b036804c534a1b2c3d4",
            "--config-root",
            str(bad_config_root),
        ],
        cwd=repo_root,
    )

    assert result.returncode == 5
    assert "config root resolves inside repository root" in result.stdout
    assert not (repo_root / "SESSION_STATE.json").exists()


@pytest.mark.governance
def test_persist_workspace_artifacts_blocks_when_binding_file_missing(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            "88b39b036804c534a1b2c3d4",
            "--config-root",
            str(cfg),
            "--quiet",
        ]
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload.get("reason_code") == "BLOCKED-MISSING-BINDING-FILE"


@pytest.mark.governance
def test_bootstrap_session_state_blocks_when_binding_file_missing(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "bootstrap_session_state.py"
    cfg = tmp_path / "opencode-config"

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            "88b39b036804c534a1b2c3d4",
            "--config-root",
            str(cfg),
        ]
    )

    assert result.returncode == 2
    assert "binding evidence" in result.stdout.lower()


@pytest.mark.governance
def test_persist_workspace_artifacts_never_creates_repo_local_c_artifact(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir()

    cfg = tmp_path / "opencode-config"
    write_governance_paths(cfg)

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            "88b39b036804c534a1b2c3d4",
            "--repo-root",
            str(repo_root),
            "--config-root",
            str(cfg),
            "--quiet",
        ],
        cwd=repo_root,
    )

    assert result.returncode == 0, f"persist helper failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
    assert not (repo_root / "C").exists(), "must never create repo-local artifact named 'C'"
    assert not (repo_root / "business-rules.md").exists(), "must never write business-rules.md into repo root"


@pytest.mark.governance
def test_persist_workspace_artifacts_allows_repo_local_config_root_for_non_git_dirs(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    repo_root = tmp_path / "artifact-extract"
    repo_root.mkdir(parents=True, exist_ok=True)

    cfg = repo_root / "_cfg"
    write_governance_paths(cfg)

    result = run(
        [
            sys.executable,
            str(script),
            "--repo-fingerprint",
            "c3d4e5f6a1b2c3d4e5f6a1b2",
            "--repo-root",
            str(repo_root),
            "--config-root",
            str(cfg),
            "--quiet",
        ],
        cwd=repo_root,
    )

    assert result.returncode == 0, f"persist helper should allow non-git artifact dirs:\n{result.stderr}\n{result.stdout}"
