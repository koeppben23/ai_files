"""OpenCode desktop/IDE plugin hook for new governance work runs.

This plugin listens for `session.created` and triggers the canonical
`governance.entrypoints.new_work_session` initializer.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping


_SEEN_SESSION_IDS: set[str] = set()


def _logger_default(level: str, message: str, **meta: object) -> None:
    payload = {"level": level, "message": message, "meta": meta}
    print(payload)


def _run_default(argv: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)


def handle_event(
    event: Mapping[str, Any],
    *,
    run_command: Callable[[list[str], str | None], Any] = _run_default,
    logger: Callable[..., None] = _logger_default,
    python_command: str | None = None,
) -> dict[str, object]:
    event_type = str(event.get("type") or "").strip()
    if event_type != "session.created":
        return {"status": "ignored", "reason": "unsupported-event"}

    session_id = str(event.get("session_id") or event.get("id") or "").strip()
    if session_id and session_id in _SEEN_SESSION_IDS:
        return {"status": "ignored", "reason": "already-processed", "session_id": session_id}

    repo_root = str(event.get("repo_root") or event.get("workspace") or os.getcwd()).strip()
    if not repo_root:
        logger("warn", "missing repo_root for session.created")
        return {"status": "ignored", "reason": "missing-repo-root"}

    exe = (python_command or sys.executable).strip() or sys.executable
    argv = [
        exe,
        "-m",
        "governance.entrypoints.new_work_session",
        "--trigger-source",
        "desktop-plugin",
        "--quiet",
    ]
    if session_id:
        argv.extend(["--session-id", session_id])

    reason = str(event.get("reason") or "").strip()
    if reason:
        argv.extend(["--reason", reason])

    try:
        result = run_command(argv, repo_root)
    except Exception as exc:
        logger("error", f"failed to start new work session: {exc}")
        return {"status": "error", "reason": "spawn-failed", "session_id": session_id}

    return_code = int(getattr(result, "returncode", 1))
    if return_code != 0:
        stderr = str(getattr(result, "stderr", ""))
        logger("error", f"new_work_session returned non-zero: rc={return_code} stderr={stderr}")
        return {"status": "error", "reason": "initializer-failed", "session_id": session_id}

    if session_id:
        _SEEN_SESSION_IDS.add(session_id)
    logger("info", f"new work session initialized: session_id={session_id}")
    return {"status": "ok", "reason": "new-work-session-created", "session_id": session_id}


def reset_seen_sessions_for_tests() -> None:
    _SEEN_SESSION_IDS.clear()
