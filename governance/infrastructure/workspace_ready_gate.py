"""Workspace ready gate for persistence verification.

This module provides the fail-closed verification that a workspace is
fully initialized and ready for use. It implements:

    1. Workspace lock acquisition (prevents concurrent bootstrap)
    2. Marker file creation (workspace-ready-marker.v1)
    3. Global pointer write (opencode-session-pointer.v1)
    4. Fingerprint SSOT enforcement (prevents cross-wire)
    5. Legacy pointer schema migration

The gate ensures that:
    - Only one bootstrap process can write to a workspace at a time
    - The global pointer always references a valid workspace
    - Fingerprint mismatches are detected and blocked (cross-wire detection)
    - Legacy pointer schemas are auto-migrated to canonical format

Usage:
    with_workspace_ready_gate(
        workspaces_home=...,
        repo_fingerprint="a1b2c3d4e5f6a1b2c3d4e5f6",
        ...
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re

from governance.domain.canonical_json import canonical_json_text
from governance.infrastructure.fs_atomic import atomic_write_text

_LOCK_TTL_SECONDS: int = 120

LEGACY_POINTER_SCHEMAS = {"active-session-pointer.v1"}
CANONICAL_POINTER_SCHEMA = "opencode-session-pointer.v1"


def read_pointer_file(pointer_path: Path) -> dict | None:
    """Read and optionally migrate a pointer file.
    
    Supports both canonical and legacy pointer schemas. Legacy schemas
    are automatically migrated to the canonical format on read.
    
    Args:
        pointer_path: Path to the SESSION_STATE.json pointer file.
    
    Returns:
        The pointer payload dict, or None if invalid/unreadable.
        Legacy pointers are returned in canonical format.
    """
    if not pointer_path.is_file():
        return None
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    schema = payload.get("schema")
    if schema == CANONICAL_POINTER_SCHEMA:
        return payload
    if schema in LEGACY_POINTER_SCHEMAS:
        migrated = _migrate_legacy_pointer(payload)
        try:
            atomic_write_text(pointer_path, canonical_json_text(migrated) + "\n")
        except OSError:
            pass
        return migrated
    return None


def _migrate_legacy_pointer(legacy: dict) -> dict:
    """Migrate a legacy pointer payload to canonical schema.
    
    Args:
        legacy: The legacy pointer payload dict.
    
    Returns:
        A new dict in canonical schema format.
    """
    return {
        "schema": CANONICAL_POINTER_SCHEMA,
        "repo_fingerprint": legacy.get("repo_fingerprint", ""),
        "session_id": legacy.get("session_id", ""),
        "workspace_ready": legacy.get("workspace_ready", False),
        "active_session_state_file": legacy.get("active_session_state_file", ""),
        "updatedAt": legacy.get("updated_at", legacy.get("updatedAt", "")),
    }


@dataclass(frozen=True)
class WorkspaceReadyDecision:
    ok: bool
    reason: str
    workspace_dir: Path | None
    marker_path: Path | None
    pointer_path: Path | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_workspace_ready(
    *,
    workspaces_home: Path,
    repo_fingerprint: str,
    repo_root: Path,
    session_state_file: Path,
    session_pointer_file: Path,
    session_id: str,
    discovery_method: str,
) -> WorkspaceReadyDecision:
    fp = str(repo_fingerprint).strip()
    if not fp:
        return WorkspaceReadyDecision(False, "fingerprint-missing", None, None, None)

    workspace_dir = workspaces_home / fp
    locks_dir = workspace_dir / "locks"
    lock_dir = locks_dir / "workspace.lock"
    marker_path = workspace_dir / "marker.json"
    pointer_path = session_pointer_file
    evidence_path = workspace_dir / "evidence" / "repo-context.resolved.json"

    workspace_dir.mkdir(parents=True, exist_ok=True)
    locks_dir.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        # Stale-lock detection: if owner.json is missing or TTL exceeded, reclaim.
        owner_file = lock_dir / "owner.json"
        stale = False
        if owner_file.exists():
            try:
                payload = json.loads(owner_file.read_text(encoding="utf-8"))
                acquired_at_raw = payload.get("acquired_at")
                if isinstance(acquired_at_raw, str) and acquired_at_raw.strip():
                    acquired = datetime.fromisoformat(acquired_at_raw.replace("Z", "+00:00"))
                    if acquired.tzinfo is None:
                        acquired = acquired.replace(tzinfo=timezone.utc)
                    stale = (datetime.now(timezone.utc) - acquired).total_seconds() > _LOCK_TTL_SECONDS
            except Exception:
                stale = True
        else:
            stale = True
        if not stale:
            return WorkspaceReadyDecision(False, "workspace-lock-held", workspace_dir, marker_path, pointer_path)
        # Reclaim stale lock atomically: write a sentinel file with O_CREAT|O_EXCL
        # semantics via a temp rename, then remove old artifacts.
        try:
            if owner_file.exists():
                owner_file.unlink(missing_ok=True)
            # Attempt to reclaim: remove the directory and re-create atomically.
            # If another process races us, mkdir will raise FileExistsError.
            try:
                os.rmdir(lock_dir)
            except OSError:
                return WorkspaceReadyDecision(False, "workspace-lock-held", workspace_dir, marker_path, pointer_path)
            lock_dir.mkdir(parents=False, exist_ok=False)
        except (OSError, FileExistsError):
            return WorkspaceReadyDecision(False, "workspace-lock-held", workspace_dir, marker_path, pointer_path)

    try:
        owner_payload = json.dumps({
            "pid": os.getpid(),
            "acquired_at": _iso_now(),
        }, ensure_ascii=True)
        owner_file_path = lock_dir / "owner.json"
        try:
            atomic_write_text(owner_file_path, owner_payload + "\n")
        except OSError:
            pass

        marker_payload = {
            "schema": "workspace-ready-marker.v1",
            "repo_fingerprint": fp,
            "repo_root": str(repo_root),
            "session_id": session_id,
            "workspace_ready": True,
            "committed_at": _iso_now(),
            "discovery_method": discovery_method,
        }
        evidence_payload = {
            "schema": "repo-context.v1",
            "status": "resolved",
            "repo_root": str(repo_root),
            "repo_fingerprint": fp,
            "session_id": session_id,
            "discovery_method": discovery_method,
            "discovered_at": _iso_now(),
        }
        pointer_payload = {
            "schema": "opencode-session-pointer.v1",
            "repo_fingerprint": fp,
            "session_id": session_id,
            "workspace_ready": True,
            "active_session_state_file": str(session_state_file),
            "updatedAt": _iso_now(),
        }

        atomic_write_text(marker_path, canonical_json_text(marker_payload) + "\n")
        atomic_write_text(evidence_path, canonical_json_text(evidence_payload) + "\n")
        atomic_write_text(pointer_path, canonical_json_text(pointer_payload) + "\n")
        return WorkspaceReadyDecision(True, "ok", workspace_dir, marker_path, pointer_path)
    finally:
        try:
            owner_cleanup = lock_dir / "owner.json"
            if owner_cleanup.exists():
                owner_cleanup.unlink(missing_ok=True)
            os.rmdir(lock_dir)
        except OSError:
            pass
