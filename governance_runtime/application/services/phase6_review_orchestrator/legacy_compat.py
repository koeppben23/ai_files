"""Legacy compatibility layer for Phase-6 review functions.

This module provides backward-compatible helpers for session_reader.py.
Only read_plan_body is used.

New code should import directly from:
- governance_runtime.application.services.phase6_review_orchestrator
"""

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
                body = payload.get("body") or payload.get("planBody") or payload.get("plan_body")
                if isinstance(body, str) and body.strip():
                    return body.strip()
    except Exception:
        pass
    return "none"
