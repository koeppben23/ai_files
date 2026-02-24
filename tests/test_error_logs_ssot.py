from __future__ import annotations

from pathlib import Path

import diagnostics.error_logs as error_logs


def test_write_error_event_uses_ssot_error_log_path(monkeypatch) -> None:
    cfg = Path("/tmp/opencode-config")
    ws = cfg / "workspaces"
    fp = "88b39b036804c534a1b2c3d4"

    monkeypatch.setattr(error_logs, "resolve_paths", lambda config_root=None: (cfg, ws))
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
    cfg = Path("/tmp/opencode-config")
    ws = cfg / "workspaces"
    fp = "88b39b036804c534a1b2c3d4"

    monkeypatch.setattr(error_logs, "resolve_paths", lambda config_root=None: (cfg, ws))
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
