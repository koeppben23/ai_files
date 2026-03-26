from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Callable


def _read_env(
    key: str,
    *,
    env_reader: Callable[[str], str | None] | None,
) -> str:
    if env_reader is None:
        return str(os.environ.get(key) or "").strip()
    return str(env_reader(key) or "").strip()


def _has_direct_binding_tokens(
    *,
    env_reader: Callable[[str], str | None] | None,
) -> bool:
    binding_tokens = (
        "OPENCODE_MODEL",
        "OPENCODE_MODEL_ID",
        "OPENCODE_MODEL_PROVIDER",
        "OPENCODE_MODEL_CONTEXT_LIMIT",
        "OPENCODE_CLIENT_MODEL",
        "OPENCODE_CLIENT_PROVIDER",
    )
    return any(_read_env(key, env_reader=env_reader) for key in binding_tokens)


def _resolve_db_path(
    *,
    env_reader: Callable[[str], str | None] | None,
    db_path: Path | None,
) -> Path | None:
    if db_path is not None:
        return db_path
    data_root = _read_env("OPENCODE_DATA_ROOT", env_reader=env_reader)
    if data_root:
        return Path(data_root) / "opencode.db"
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _resolve_session_id_from_guard(
    *,
    env_reader: Callable[[str], str | None] | None,
) -> str:
    config_root = _read_env("OPENCODE_CONFIG_ROOT", env_reader=env_reader)
    if config_root:
        config_path = Path(config_root)
    else:
        config_path = Path.home() / ".config" / "opencode"

    pointer_path = config_path / "SESSION_STATE.json"
    if not pointer_path.exists():
        return ""
    try:
        pointer_doc = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    session_state_file = str(pointer_doc.get("activeSessionStateFile") or "").strip()
    if not session_state_file:
        return ""

    workspace_home = Path(session_state_file).parent
    guard_path = workspace_home / ".new_work_guard.json"
    if not guard_path.exists():
        return ""
    try:
        guard_doc = json.loads(guard_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    last = guard_doc.get("last")
    if not isinstance(last, dict):
        return ""
    return str(last.get("session_id") or "").strip()


def _extract_model_from_message_payload(payload: str) -> tuple[str, str] | None:
    try:
        data = json.loads(payload)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    provider = str(data.get("providerID") or "").strip()
    model_id = str(data.get("modelID") or "").strip()
    if provider and model_id:
        return provider, model_id

    nested_model = data.get("model")
    if isinstance(nested_model, dict):
        nested_provider = str(
            nested_model.get("providerID")
            or nested_model.get("providerId")
            or nested_model.get("provider")
            or ""
        ).strip()
        nested_model_id = str(
            nested_model.get("modelID")
            or nested_model.get("modelId")
            or nested_model.get("id")
            or ""
        ).strip()
        if nested_provider and nested_model_id:
            return nested_provider, nested_model_id

    return None


def resolve_active_opencode_model(
    *,
    env_reader: Callable[[str], str | None] | None = None,
    cwd: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, str] | None:
    """Resolve active OpenCode model identity from local OpenCode session storage."""
    resolved_db_path = _resolve_db_path(env_reader=env_reader, db_path=db_path)
    if resolved_db_path is None or not resolved_db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(resolved_db_path))
    except Exception:
        return None

    try:
        session_id = _read_env("OPENCODE_SESSION_ID", env_reader=env_reader)
        if not session_id:
            session_id = _resolve_session_id_from_guard(env_reader=env_reader)
        session_id = session_id.strip()
        if not session_id:
            return None

        rows = conn.execute(
            "SELECT data FROM message WHERE session_id = ? ORDER BY time_updated DESC LIMIT 200",
            (session_id,),
        ).fetchall()
        for row in rows:
            payload = str(row[0] or "")
            model_tuple = _extract_model_from_message_payload(payload)
            if model_tuple is None:
                continue
            provider, model_id = model_tuple
            return {
                "session_id": session_id,
                "provider": provider,
                "model_id": model_id,
                "source": "opencode.db",
            }
    except Exception:
        return None
    finally:
        conn.close()

    return None


def has_active_desktop_llm_binding(
    *,
    env_reader: Callable[[str], str | None] | None = None,
    cwd: Path | None = None,
    db_path: Path | None = None,
) -> bool:
    """Return True when OpenCode Desktop has an active model binding."""
    if _has_direct_binding_tokens(env_reader=env_reader):
        return True
    return resolve_active_opencode_model(
        env_reader=env_reader,
        cwd=cwd,
        db_path=db_path,
    ) is not None
