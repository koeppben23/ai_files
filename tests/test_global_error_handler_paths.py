from __future__ import annotations

import json
from pathlib import Path

import diagnostics.global_error_handler as geh
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


def test_emit_gate_failure_supports_legacy_event_sink_signature(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "cfg"
    captured = {"called": False}

    def legacy_write(path: Path, event: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        captured["called"] = True

    monkeypatch.setattr(geh, "write_jsonl_event", legacy_write)

    ok = emit_gate_failure(
        gate="PERSISTENCE",
        code="BLOCKED-WORKSPACE-PERSISTENCE",
        message="legacy",
        config_root=config_root,
        workspaces_home=tmp_path / "workspaces",
        repo_fingerprint=None,
    )

    assert ok is True
    assert captured["called"] is True


def test_resolve_log_path_prefers_commands_home_before_config_root(tmp_path: Path) -> None:
    config_root = tmp_path / "cfg"
    commands_home = tmp_path / "commands"

    path = resolve_log_path(
        config_root=config_root,
        commands_home=commands_home,
        workspaces_home=tmp_path / "workspaces",
        repo_fingerprint=None,
    )

    assert path == commands_home / "logs" / "error.log.jsonl"
