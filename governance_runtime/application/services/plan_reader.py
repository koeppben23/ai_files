"""Plan reader service for reading plan content from plan-record files."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def read_plan_body(session_path: Path, json_loader: Callable[[Path], dict] | None = None) -> str:
    """Read plan body from plan-record.json.

    Args:
        session_path: Path to the session file.
        json_loader: Injectable JSON loader (for testing). If None,
                    raises ValueError to enforce architecture rules.
    """
    if json_loader is None:
        raise ValueError("json_loader is required for read_plan_body (inject load_json from infrastructure)")
    try:
        plan_record_path = session_path.parent / "plan-record.json"
        if plan_record_path.is_file():
            payload = json_loader(plan_record_path)
            if isinstance(payload, dict):
                versions = payload.get("versions")
                if isinstance(versions, list) and versions:
                    latest = versions[-1] if isinstance(versions[-1], dict) else {}
                    if isinstance(latest, dict):
                        body = latest.get("plan_record_text")
                        if isinstance(body, str) and body.strip():
                            return body.strip()
    except Exception:
        pass
    return "none"
