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
    - Pointer is read by governance, runtime gates, and phase routers
    - Two different key formats = kernel breaker (readers fail silently)
    - Migration path for legacy formats is defined here

Migration from legacy keys:
    - repo_fingerprint -> activeRepoFingerprint
    - active_session_state_file -> activeSessionStateFile
    - active_session_state_relative_path -> activeSessionStateRelativePath
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

CANONICAL_POINTER_SCHEMA = "opencode-session-pointer.v1"
LEGACY_POINTER_SCHEMAS = {"active-session-pointer.v1"}

FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{24}$")
_POINTER_KEYS = frozenset(
    {
        "activeRepoFingerprint",
        "repo_fingerprint",
        "activeSessionStateFile",
        "active_session_state_file",
        "activeSessionStateRelativePath",
        "active_session_state_relative_path",
    }
)


def is_session_pointer_document(payload: object) -> bool:
    """Return True when *payload* is pointer-shaped, not session-state-shaped."""

    if not isinstance(payload, Mapping):
        return False
    if isinstance(payload.get("SESSION_STATE"), Mapping):
        return False

    schema = payload.get("schema")
    if isinstance(schema, str) and schema in {CANONICAL_POINTER_SCHEMA} | LEGACY_POINTER_SCHEMAS:
        return True

    return any(key in payload for key in _POINTER_KEYS)


def parse_session_pointer_document(payload: object) -> dict[str, str]:
    """Parse a pointer document for read paths.

    This parser is intentionally more tolerant than ``parse_pointer_payload``:
    it accepts legacy schemas/keys and allows resolving from either the
    absolute session-state path or the relative workspace path. Writer and
    validation paths must continue to use ``parse_pointer_payload``.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("Session pointer document must be a JSON object")
    if isinstance(payload.get("SESSION_STATE"), Mapping):
        raise ValueError("Document is a materialized session state, not a session pointer")

    schema = payload.get("schema")
    if isinstance(schema, str) and schema not in {CANONICAL_POINTER_SCHEMA} | LEGACY_POINTER_SCHEMAS:
        raise ValueError(f"Unknown pointer schema: {schema}")
    if schema is None and not any(key in payload for key in _POINTER_KEYS):
        raise ValueError("Document is not a session pointer")

    result: dict[str, str] = {"schema": CANONICAL_POINTER_SCHEMA}

    fingerprint = _normalize_read_fingerprint(_extract_fingerprint(payload))
    session_file = _extract_session_state_file(payload)
    relative_path = _extract_relative_path(payload)

    if session_file:
        session_file_text = str(session_file).strip()
        if not os.path.isabs(session_file_text):
            raise ValueError("Pointer field 'activeSessionStateFile' must be absolute")
        result["activeSessionStateFile"] = Path(session_file_text).resolve(strict=False).as_posix()

    if relative_path:
        result["activeSessionStateRelativePath"] = _normalize_relative_path(relative_path)

    if "activeSessionStateFile" not in result and "activeSessionStateRelativePath" not in result:
        raise ValueError("Pointer contains no session state file path")

    if fingerprint:
        result["activeRepoFingerprint"] = fingerprint

    updated_at = _extract_updated_at(payload)
    if updated_at:
        result["updatedAt"] = updated_at.strip()

    return result


def resolve_active_session_state_path(pointer: Mapping[str, Any], *, config_root: Path) -> Path:
    """Resolve the active workspace session-state path from a parsed pointer."""

    parsed = parse_session_pointer_document(pointer)

    absolute_path = parsed.get("activeSessionStateFile", "").strip()
    relative_path = parsed.get("activeSessionStateRelativePath", "").strip()

    resolved_relative: Path | None = None
    if relative_path:
        resolved_relative = (config_root / Path(relative_path)).resolve(strict=False)

    resolved_absolute: Path | None = None
    if absolute_path:
        if not os.path.isabs(absolute_path):
            raise ValueError("Pointer field 'activeSessionStateFile' must be absolute")
        resolved_absolute = Path(absolute_path).resolve(strict=False)

    if resolved_absolute is not None and resolved_relative is not None and resolved_absolute != resolved_relative:
        raise ValueError("Pointer absolute and relative session-state paths disagree")
    if resolved_absolute is not None:
        return resolved_absolute
    if resolved_relative is not None:
        return resolved_relative
    raise ValueError("Pointer contains no session state file path")


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
        payload["activeSessionStateFile"] = session_state_file.resolve().as_posix()
        
        if config_root is not None:
            try:
                rel_path = session_state_file.relative_to(config_root)
                payload["activeSessionStateRelativePath"] = rel_path.as_posix()
            except ValueError:
                pass
    else:
        payload["activeSessionStateRelativePath"] = f"workspaces/{fp}/SESSION_STATE.json"
    
    return payload


def parse_pointer_payload(payload: dict) -> dict:
    """Parse and validate a pointer payload for write/validation paths.

    This parser is intentionally strict: canonical 24-hex fingerprints,
    canonical relative path, and an absolute session-state path are required.
    """
    if not isinstance(payload, dict):
        return {}
    
    schema = payload.get("schema")
    
    if schema not in {CANONICAL_POINTER_SCHEMA} | LEGACY_POINTER_SCHEMAS:
        return {}
    
    result = {"schema": CANONICAL_POINTER_SCHEMA}
    
    fp = _extract_fingerprint(payload)
    if not fp:
        return {}
    try:
        result["activeRepoFingerprint"] = validate_fingerprint(fp)
    except ValueError:
        return {}
    
    session_file = _extract_session_state_file(payload)
    if not session_file:
        return {}
    session_file_text = str(session_file).strip()
    session_file_path = Path(session_file_text)
    if not os.path.isabs(session_file_text):
        return {}
    result["activeSessionStateFile"] = str(session_file_path)
    
    rel_path = _extract_relative_path(payload)
    expected_rel = f"workspaces/{result['activeRepoFingerprint']}/SESSION_STATE.json"
    if not rel_path:
        if str(session_file_path).replace("\\", "/").endswith(expected_rel):
            normalized_rel = expected_rel
        else:
            return {}
    else:
        normalized_rel = str(rel_path).replace("\\", "/")
        if normalized_rel != expected_rel:
            return {}
    result["activeSessionStateRelativePath"] = normalized_rel

    if not str(session_file_path).replace("\\", "/").endswith(expected_rel):
        return {}
    
    updated_at = _extract_updated_at(payload)
    if updated_at:
        result["updatedAt"] = updated_at
    
    return result


def _extract_fingerprint(payload: Mapping[str, Any]) -> str | None:
    """Extract fingerprint from canonical or legacy keys."""
    for key in ("activeRepoFingerprint", "repo_fingerprint"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_session_state_file(payload: Mapping[str, Any]) -> str | None:
    """Extract session state file from canonical or legacy keys."""
    for key in ("activeSessionStateFile", "active_session_state_file"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_relative_path(payload: Mapping[str, Any]) -> str | None:
    """Extract relative path from canonical or legacy keys."""
    for key in ("activeSessionStateRelativePath", "active_session_state_relative_path"):
        if key in payload:
            return str(payload[key])
    return None


def _extract_updated_at(payload: Mapping[str, Any]) -> str | None:
    """Extract updated_at timestamp from canonical or legacy keys."""
    for key in ("updatedAt", "updated_at"):
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
    session_file = payload.get("activeSessionStateFile")
    rel_path = payload.get("activeSessionStateRelativePath")
    if not fp or not session_file or not rel_path:
        return False

    try:
        fp = validate_fingerprint(str(fp))
    except ValueError:
        return False

    session_file_text = str(session_file)
    session_file_path = Path(session_file_text)
    if not os.path.isabs(session_file_text):
        return False

    rel_normalized = str(rel_path).replace("\\", "/")
    expected_rel = f"workspaces/{fp}/SESSION_STATE.json"
    if rel_normalized != expected_rel:
        return False

    return str(session_file_path).replace("\\", "/").endswith(expected_rel)


def _normalize_read_fingerprint(value: str | None) -> str:
    probe = str(value or "").strip()
    if not probe:
        return ""
    normalized = probe.lower()
    if FINGERPRINT_PATTERN.fullmatch(normalized):
        return normalized
    return probe


def _normalize_relative_path(value: str) -> str:
    normalized = str(value).strip().replace("\\", "/")
    if not normalized:
        raise ValueError("Pointer contains no session state file path")
    if os.path.isabs(normalized):
        raise ValueError("Pointer field 'activeSessionStateRelativePath' must be relative")

    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Pointer field 'activeSessionStateRelativePath' must stay inside config root")
    return "/".join(parts)

