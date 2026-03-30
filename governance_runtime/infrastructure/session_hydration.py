#!/usr/bin/env python3
"""Shared session hydration check utilities.

This module provides common functionality for checking whether a governance
session has been hydrated (bound to an OpenCode session).

Soft Blocking Architecture:
- For read-only commands (/review): check session_hydrated field in snapshot
- For mutating commands (/ticket, /plan): use require_hydrated() hard blocking

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

HYDRATION_STATUS_HYDRATED = "hydrated"


def get_session_hydration_status(state: Mapping[str, Any]) -> str:
    """Get the hydration status from session state.

    Args:
        state: Session state dictionary.

    Returns:
        "hydrated" if session is hydrated, "not_hydrated" otherwise.
    """
    hydration = state.get("SessionHydration")
    if not isinstance(hydration, dict):
        return "not_hydrated"
    return hydration.get("status", "not_hydrated")


def is_session_hydrated(state: Mapping[str, Any]) -> bool:
    """Check if session has been hydrated.

    Args:
        state: Session state dictionary.

    Returns:
        True if session is hydrated, False otherwise.
    """
    return get_session_hydration_status(state) == HYDRATION_STATUS_HYDRATED


def require_hydrated(state: Mapping[str, Any], command: str) -> bool:
    """Require that the session is hydrated, printing blocked payload if not.

    This function provides a convenient way to block governance commands
    that require a hydrated session. Prints JSON payload and returns False
    if not hydrated. Caller should exit with appropriate code.

    Args:
        state: Session state dictionary.
        command: Name of the command (e.g., "/ticket", "/review").

    Returns:
        True if session is hydrated, False otherwise.
    """
    if not is_session_hydrated(state):
        payload = {
            "status": "blocked",
            "reason": "session-not-hydrated",
            "reason_code": f"BLOCKED-{command.upper().replace('/','')}-NOT-HYDRATED",
            "recovery_action": f"run /hydrate first to bind governance session to OpenCode session",
            "next_action": "run /hydrate.",
            "next_action_command": "/hydrate",
        }
        print(json.dumps(payload, ensure_ascii=True), file=sys.stdout)
        return False
    return True


def resolve_session_state() -> Mapping[str, Any]:
    """Resolve session state from the active session.

    Returns:
        Session state dictionary, or empty dict if unavailable.
    """
    try:
        from governance_runtime.infrastructure.session_locator import resolve_active_session_paths
        from governance_runtime.infrastructure.json_store import load_json

        session_path, _, _, _ = resolve_active_session_paths()
        document = load_json(session_path)
        return document.get("SESSION_STATE", {})
    except Exception:
        return {}


def get_hydration_guard_state() -> Mapping[str, Any]:
    """Resolve session state and check hydration status.

    Convenience function that resolves session state and checks hydration.
    Returns session state (may be empty) for caller to handle.

    Args:
        None

    Returns:
        Session state dictionary (may be empty if resolution fails).
    """
    return resolve_session_state()
