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
    OPENCODE_MODE: Explicit operating mode (user|pipeline|agents_strict)
    OPENCODE_DIAGNOSTICS_MODE: Deprecated fallback mode label for diagnostics metadata

Write Policy (unified):
    Writes are allowed by default, unless FORCE_READ_ONLY=1
    
    This matches the expected behavior for "/start persists always":
    - User mode: writes allowed (default)
    - Pipeline mode: writes allowed (default)
    - FORCE_READ_ONLY=1: writes blocked always

This unifies the previous inconsistent policies:
- Old persist_workspace_artifacts.py: READ_ONLY = True unless ALLOW_WRITE=1
- Old bootstrap_session_state.py: writes allowed unless FORCE_READ_ONLY=1

The unified policy follows the bootstrap behavior: writes allowed unless explicitly blocked.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


import os

try:
    from governance.domain.policies.write_policy import compute_write_policy
except Exception:
    def compute_write_policy(*, force_read_only: bool, mode: str = "user"):
        normalized_mode = str(mode or "user").strip().lower()
        if normalized_mode not in {"user", "pipeline", "agents_strict"}:
            normalized_mode = "user"
        if force_read_only:
            return type("WritePolicy", (), {"writes_allowed": False, "reason": "force-read-only", "mode": normalized_mode})()
        return type(
            "WritePolicy",
            (),
            {"writes_allowed": True, "reason": f"explicit-{normalized_mode}-mode-allow", "mode": normalized_mode},
        )()


def effective_mode() -> str:
    primary = os.environ.get("OPENCODE_MODE", "").strip()
    if primary:
        return primary
    fallback = os.environ.get("OPENCODE_DIAGNOSTICS_MODE", "").strip()
    if fallback:
        return fallback
    return "user"


EFFECTIVE_MODE = effective_mode()


def write_policy_reasons() -> tuple[str, ...]:
    reasons: list[str] = [f"mode:{effective_mode()}"]
    policy = compute_write_policy(
        force_read_only=str(os.environ.get("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "")).strip() == "1",
        mode=effective_mode(),
    )
    reasons.append(policy.reason)
    return tuple(reasons)


def writes_allowed() -> bool:
    """Check if write operations are permitted.
    
    Returns:
        True if writes are allowed, False if read-only mode is enforced.
    
    Write Policy (unified):
        Writes are allowed by default, unless FORCE_READ_ONLY=1
    """
    return compute_write_policy(
        force_read_only=str(os.environ.get("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "")).strip() == "1",
        mode=effective_mode(),
    ).writes_allowed


def is_write_allowed() -> bool:
    """Alias for writes_allowed() for clarity.
    
    Returns:
        True if writes are allowed, False if read-only mode is enforced.
    """
    return writes_allowed()
