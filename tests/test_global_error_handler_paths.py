from __future__ import annotations

import json
from pathlib import Path

from diagnostics.global_error_handler import emit_gate_failure, resolve_log_path


def test_emit_gate_failure_without_fingerprint_writes_global_log(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    workspaces_home = tmp_path / "workspaces"
    workspaces_home.mkdir(parents=True, exist_ok=True)

    ok = emit_gate_failure(
        gate="PERSISTENCE",
        code="BLOCKED-REPO-ROOT-NOT-DETECTABLE",
        message="x",
        config_root=config_root,
        workspaces_home=workspaces_home,
        repo_fingerprint=None,
    )
    assert ok is True
    path = resolve_log_path(config_root=config_root, workspaces_home=workspaces_home, repo_fingerprint=None)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    assert json.loads(lines[-1])["code"] == "BLOCKED-REPO-ROOT-NOT-DETECTABLE"


def test_emit_gate_failure_with_fingerprint_writes_workspace_log(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    workspaces_home = tmp_path / "workspaces"
    repo_fp = "88b39b036804c534a1b2c3d4"

    ok = emit_gate_failure(
        gate="PERSISTENCE",
        code="BLOCKED-WORKSPACE-PERSISTENCE",
        message="x",
        config_root=config_root,
        workspaces_home=workspaces_home,
        repo_fingerprint=repo_fp,
    )
    assert ok is True
    path = resolve_log_path(config_root=config_root, workspaces_home=workspaces_home, repo_fingerprint=repo_fp)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    assert json.loads(lines[-1])["context"]["fp"] == repo_fp
