"""Canonical session pointer SSOT - Single Source of Truth.

This module defines the ONE AND ONLY valid format for opencode-session-pointer.v1.
All writers and readers of session pointers MUST use this module.

Schema: opencode-session-pointer.v1
Canonical Keys (binding):
    - schema: "opencode-session-pointer.v1"
    - activeRepoFingerprint: 24-hex canonical fingerprint
    - activeSessionStateFile: absolute path to SESSION_STATE.json
    - activeSessionStateRelativePath: relative path from config root

Why SSOT matters:
    - Pointer is read by diagnostics, runtime gates, and phase routers
    - Two different key formats = kernel breaker (readers fail silently)
    - Migration path for legacy formats is defined here

Migration from legacy keys:
    - repo_fingerprint -> activeRepoFingerprint
    - active_session_state_file -> activeSessionStateFile
    - active_session_state_relative_path -> activeSessionStateRelativePath
"""
from __future__ import annotations

import re
from pathlib import Path

CANONICAL_POINTER_SCHEMA = "opencode-session-pointer.v1"
LEGACY_POINTER_SCHEMAS = {"active-session-pointer.v1"}

FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{24}$")


def validate_fingerprint(fp: str) -> str:
    """Validate and normalize a repo fingerprint.
    
    Args:
        fp: The fingerprint string to validate.
    
    Returns:
        The validated fingerprint (lowercase, stripped).
    
    Raises:
        ValueError: If fingerprint is not a valid 24-hex string.
    """
    normalized = str(fp).strip().lower()
    if not FINGERPRINT_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"Invalid repo fingerprint: expected 24 lowercase hex chars, got {fp!r}"
        )
    return normalized


def build_pointer_payload(
    repo_fingerprint: str,
    session_state_file: Path | None = None,
    config_root: Path | None = None,
    updated_at: str | None = None,
) -> dict:
    """Build a canonical pointer payload.
    
    This is the ONLY function that should be used to create pointer payloads.
    All writers MUST use this function to ensure format consistency.
    
    Args:
        repo_fingerprint: The canonical 24-hex fingerprint for this repository.
        session_state_file: Optional absolute path to SESSION_STATE.json.
        config_root: Optional config root for computing relative path.
        updated_at: Optional ISO timestamp for when the pointer was updated.
    
    Returns:
        A canonical pointer payload dict with schema opencode-session-pointer.v1.
    
    Raises:
        ValueError: If repo_fingerprint is not valid 24-hex.
    """
    fp = validate_fingerprint(repo_fingerprint)
    
    payload = {
        "schema": CANONICAL_POINTER_SCHEMA,
        "activeRepoFingerprint": fp,
    }
    
    if updated_at is not None:
        payload["updatedAt"] = updated_at
    
    if session_state_file is not None:
        payload["activeSessionStateFile"] = str(session_state_file)
        
        if config_root is not None:
            try:
                rel_path = session_state_file.relative_to(config_root)
                payload["activeSessionStateRelativePath"] = str(rel_path)
            except ValueError:
                pass
    else:
        payload["activeSessionStateRelativePath"] = f"workspaces/{fp}/SESSION_STATE.json"
    
    return payload


def parse_pointer_payload(payload: dict) -> dict:
    """Parse and optionally migrate a pointer payload to canonical format.
    
    Supports both canonical and legacy key formats. Legacy formats are
    normalized to canonical keys on read.
    
    Args:
        payload: The raw pointer payload dict.
    
    Returns:
        A canonical pointer payload dict, or empty dict if invalid.
    """
    if not isinstance(payload, dict):
        return {}
    
    schema = payload.get("schema")
    
    if schema not in {CANONICAL_POINTER_SCHEMA} | LEGACY_POINTER_SCHEMAS:
        return {}
    
    result = {"schema": CANONICAL_POINTER_SCHEMA}
    
    fp = _extract_fingerprint(payload)
    if fp:
        try:
            result["activeRepoFingerprint"] = validate_fingerprint(fp)
        except ValueError:
            return {}
    
    session_file = _extract_session_state_file(payload)
    if session_file:
        result["activeSessionStateFile"] = session_file
    
    rel_path = _extract_relative_path(payload)
    if rel_path:
        result["activeSessionStateRelativePath"] = rel_path
    
    updated_at = _extract_updated_at(payload)
    if updated_at:
        result["updatedAt"] = updated_at
    
    return result


def _extract_fingerprint(payload: dict) -> str | None:
    """Extract fingerprint from canonical or legacy keys."""
    for key in ("activeRepoFingerprint", "repo_fingerprint"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_session_state_file(payload: dict) -> str | None:
    """Extract session state file from canonical or legacy keys."""
    for key in ("activeSessionStateFile", "active_session_state_file"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_relative_path(payload: dict) -> str | None:
    """Extract relative path from canonical or legacy keys."""
    for key in ("activeSessionStateRelativePath", "active_session_state_relative_path"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_updated_at(payload: dict) -> str | None:
    """Extract updated_at timestamp from canonical or legacy keys."""
    for key in ("updatedAt", "updated_at"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_session_state_file(payload: dict) -> str | None:
    """Extract session state file from canonical or legacy keys."""
    for key in ("activeSessionStateFile", "active_session_state_file"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_relative_path(payload: dict) -> str | None:
    """Extract relative path from canonical or legacy keys."""
    for key in ("activeSessionStateRelativePath", "active_session_state_relative_path"):
        if key in payload:
            return str(payload[key])
    return None


def is_valid_pointer(payload: dict) -> bool:
    """Check if a payload is a valid canonical pointer.
    
    Args:
        payload: The payload to validate.
    
    Returns:
        True if the payload is a valid canonical pointer.
    """
    if not isinstance(payload, dict):
        return False
    
    if payload.get("schema") != CANONICAL_POINTER_SCHEMA:
        return False
    
    fp = payload.get("activeRepoFingerprint")
    if not fp:
        return False
    
    try:
        validate_fingerprint(fp)
    except ValueError:
        return False
    
    return True
