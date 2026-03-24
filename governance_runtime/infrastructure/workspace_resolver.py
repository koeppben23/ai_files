"""Workspace Resolver — Centralized workspace directory resolution.

Provides a single function to resolve workspace directory from session state,
consolidating logic that was previously distributed across session_locator,
phase_kernel, and other modules.

Design:
    - Single source of truth for workspace resolution
    - Uses BindingEvidenceResolver for path configuration
    - Raises RuntimeError if workspace cannot be determined
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
)


def _extract_fingerprint_from_state(state: Mapping[str, object]) -> str:
    """Extract fingerprint from state dict.
    
    Checks common field names for repository fingerprint.
    """
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def resolve_workspace_dir_from_state(
    state: Mapping[str, object],
    *,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve workspace directory from session state.

    Uses BindingEvidenceResolver to get workspaces_home, then combines with
    fingerprint extracted from state.

    Args:
        state: Session state dict (may contain RepoFingerprint or repo_fingerprint)
        env: Optional environment dict. If None, uses os.environ.

    Returns:
        Path to workspace directory, or None if fingerprint unavailable.

    Raises:
        RuntimeError: If binding evidence is unavailable.
    """
    fingerprint = _extract_fingerprint_from_state(state)
    if not fingerprint:
        return None

    resolver_env = dict(env) if env is not None else os.environ
    evidence = BindingEvidenceResolver(env=resolver_env).resolve(mode="system")
    
    if evidence.workspaces_home is None:
        return None
    
    return evidence.workspaces_home / fingerprint


def resolve_workspace_dir_from_pointer(
    config_root: Path,
    pointer: dict,
) -> Path | None:
    """Derive workspace_dir from config_root and session pointer.

    Supports both:
    - activeRepoFingerprint (preferred) -> config_root/workspaces/{fingerprint}
    - activeSessionStateFile (legacy) -> parent dir of the absolute path

    Args:
        config_root: Path to config root directory.
        pointer: Parsed session pointer dict.

    Returns:
        Path to workspace directory, or None if fingerprint unavailable.
    """
    fingerprint = pointer.get("activeRepoFingerprint")
    if fingerprint:
        return config_root / "workspaces" / str(fingerprint)
    
    session_state_file = pointer.get("activeSessionStateFile")
    if session_state_file:
        session_path = Path(session_state_file)
        if session_path.is_absolute():
            return session_path.parent
        return None
    
    return None


__all__ = [
    "resolve_workspace_dir_from_state",
    "resolve_workspace_dir_from_pointer",
]
