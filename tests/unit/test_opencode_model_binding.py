from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from governance_runtime.infrastructure.opencode_model_binding import (
    has_active_desktop_llm_binding,
    resolve_active_opencode_model,
)


def _write_active_session_pointer(config_root: Path, workspace_dir: Path) -> None:
    payload = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "repo-123",
        "activeSessionStateFile": str(workspace_dir / "SESSION_STATE.json"),
    }
    (config_root / "SESSION_STATE.json").write_text(
        json.dumps(payload, ensure_ascii=True),
        encoding="utf-8",
    )


def _write_guard(workspace_dir: Path, session_id: str) -> None:
    payload = {
        "schema": "governance.new-work-guard.v1",
        "last": {
            "session_id": session_id,
            "trigger_source": "desktop-plugin",
        },
    }
    (workspace_dir / ".new_work_guard.json").write_text(
        json.dumps(payload, ensure_ascii=True),
        encoding="utf-8",
    )


def _seed_db(db_path: Path, *, session_id: str, payload: dict[str, object]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE message (
                id TEXT,
                session_id TEXT,
                time_created INTEGER,
                time_updated INTEGER,
                data TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
            (
                "msg-1",
                session_id,
                1,
                2,
                json.dumps(payload, ensure_ascii=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_has_binding_true_when_env_model_token_present() -> None:
    env = {"OPENCODE_MODEL": "openai/gpt-5.3-codex"}
    assert has_active_desktop_llm_binding(env_reader=lambda key: env.get(key)) is True


def test_resolves_active_model_from_guarded_session_and_db(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    workspace_dir = tmp_path / "workspace"
    config_root.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "SESSION_STATE.json").write_text("{}", encoding="utf-8")

    _write_active_session_pointer(config_root, workspace_dir)
    _write_guard(workspace_dir, session_id="ses_abc")

    db_path = tmp_path / "opencode.db"
    _seed_db(
        db_path,
        session_id="ses_abc",
        payload={"role": "assistant", "providerID": "openai", "modelID": "gpt-5.3-codex"},
    )

    env = {
        "OPENCODE_CONFIG_ROOT": str(config_root),
    }

    resolved = resolve_active_opencode_model(
        env_reader=lambda key: env.get(key),
        db_path=db_path,
    )
    assert resolved is not None
    assert resolved["session_id"] == "ses_abc"
    assert resolved["provider"] == "openai"
    assert resolved["model_id"] == "gpt-5.3-codex"
    assert has_active_desktop_llm_binding(
        env_reader=lambda key: env.get(key),
        db_path=db_path,
    ) is True


def test_has_binding_false_without_env_or_guard(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    _seed_db(
        db_path,
        session_id="ses_unused",
        payload={"role": "assistant", "providerID": "openai", "modelID": "gpt-5.3-codex"},
    )
    env: dict[str, str] = {}
    assert has_active_desktop_llm_binding(
        env_reader=lambda key: env.get(key),
        db_path=db_path,
    ) is False
