"""Canonical Write Policy SSOT for diagnostics scripts.

This module defines the ONE AND ONLY write policy for all diagnostics scripts.
to ensure consistent behavior across:
- bootstrap_session_state.py
- persist_workspace_artifacts.py
- start_preflight_readonly.py
- start_persistence_hook.py

All diagnostics MUST use this module to determine write permissions.

Environment Variables:
    OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY: Set to "1" to block all writes
    CI: If set (non-empty), enables pipeline mode (READ_ONLY)
    OPENCODE_DIAGNOSTICS_ALLOW_WRITE: (DEPRECATED - use FORCE_READ_ONLY instead)

Write Policy:
    In user mode: writes are allowed by default (unless FORCE_READ_ONLY=1)
    In pipeline mode: writes are blocked by default (unless FORCE_READ_ONLY=1)

This replaces the previous inconsistent policies:
where bootstrap used ALLOW_WRITE and persist_workspace_artifacts
used ALLOW_WRITE != "1" with READ_ONLY = True.
"""
from __future__ import annotations

import os
from typing import Final

_is_pipeline: Final[bool] = os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no", "off"}
EFFECTIVE_MODE: Final[str] = "pipeline" if _is_pipeline else "user"


def writes_allowed() -> bool:
    """Check if write operations are permitted.
    
    Returns:
        True if writes are allowed, False if read-only mode is enforced.
    
    Write Policy:
        - User mode: writes allowed (default)
        - Pipeline mode: writes blocked (default)
        - FORCE_READ_ONLY=1: writes blocked always
    """
    if str(os.environ.get("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "")).strip() == "1":
        return False
    return True


def is_write_allowed() -> bool:
    """Alias for writes_allowed() for clarity.
    
    Returns:
        True if writes are allowed, False if read-only mode is enforced.
    """
    return writes_allowed()
