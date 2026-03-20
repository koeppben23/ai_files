from __future__ import annotations

from pathlib import Path
import json
import sys

import governance_runtime.infrastructure.logging.error_logs as error_logs


def test_write_error_event_uses_ssot_error_log_path(monkeypatch) -> None:
    cfg = Path("/mock/opencode-config")
    ws = cfg / "workspaces"
    fp = "88b39b036804c534a1b2c3d4"

    monkeypatch.setattr(error_logs, "resolve_paths_full", lambda config_root=None: (cfg, ws, cfg / "commands"))
    monkeypatch.setattr(error_logs, "_read_only", lambda: False)
    monkeypatch.setattr(
        error_logs,
        "resolve_ssot_log_path",
        lambda **kwargs: ws / fp / "logs" / "error.log.jsonl",
    )
    monkeypatch.setattr(error_logs, "emit_error_event_ssot", lambda **kwargs: True)

    path = error_logs.write_error_event(
        reason_key="BLOCKED-WORKSPACE-PERSISTENCE",
        message="x",
        repo_fingerprint=fp,
        gate="PERSISTENCE",
    )

    assert path.name == "error.log.jsonl"


def test_write_error_event_does_not_use_legacy_indexer(monkeypatch) -> None:
    cfg = Path("/mock/opencode-config")
    ws = cfg / "workspaces"
    fp = "88b39b036804c534a1b2c3d4"

    monkeypatch.setattr(error_logs, "resolve_paths_full", lambda config_root=None: (cfg, ws, cfg / "commands"))
    monkeypatch.setattr(error_logs, "_read_only", lambda: False)
    monkeypatch.setattr(error_logs, "resolve_ssot_log_path", lambda **kwargs: ws / fp / "logs" / "error.log.jsonl")
    monkeypatch.setattr(error_logs, "emit_error_event_ssot", lambda **kwargs: True)
    monkeypatch.setattr(error_logs, "_update_error_index", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy indexer must not run")))

    path = error_logs.write_error_event(
        reason_key="BLOCKED-WORKSPACE-PERSISTENCE",
        message="x",
        repo_fingerprint=fp,
        gate="PERSISTENCE",
    )

    assert path.name == "error.log.jsonl"


def test_resolve_paths_full_returns_commands_home(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    commands_home = cfg / "commands"
    workspaces_home = cfg / "workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": sys.executable,
        },
    }
    (cfg / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    resolved_cfg, resolved_ws, resolved_cmd = error_logs.resolve_paths_full(cfg)

    assert resolved_cfg == cfg
    assert resolved_ws == workspaces_home
    assert resolved_cmd == commands_home
