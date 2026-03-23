from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.workspace_paths import current_run_path

_POINTER_SCHEMA = "governance.current-run-pointer.v1"


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    atomic_write_text(path, text)


def read_active_run_id(*, workspaces_home: Path, repo_fingerprint: str) -> str:
    path = current_run_path(workspaces_home, repo_fingerprint)
    if not path.exists() or not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    run_id = payload.get("active_run_id")
    if isinstance(run_id, str):
        return run_id.strip()
    return ""


def write_current_run_pointer(
    *,
    workspaces_home: Path,
    repo_fingerprint: str,
    active_run_id: str,
    updated_at: str,
    activation_reason: str,
) -> Path:
    run_id = (active_run_id or "").strip()
    if not run_id:
        raise ValueError("active_run_id must be non-empty")
    payload = {
        "schema": _POINTER_SCHEMA,
        "repo_fingerprint": repo_fingerprint,
        "active_run_id": run_id,
        "updated_at": updated_at,
        "activation_reason": (activation_reason or "").strip() or "unknown",
    }
    path = current_run_path(workspaces_home, repo_fingerprint)
    _write_json_atomic(path, payload)
    return path
