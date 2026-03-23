"""Session locator — resolves active workspace session paths.

Replaces duplicated _resolve_active_session_path() across entrypoints.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.json_store import load_json
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)


def resolve_active_session_paths(
    *, env: Mapping[str, str] | None = None,
) -> tuple[Path, str, Path, Path]:
    """Resolve the active session path, fingerprint, and workspace directory.

    Returns (session_path, fingerprint, workspaces_home, workspace_dir).
    Raises RuntimeError when binding evidence is unavailable.

    Callers that need events_path can derive it as workspace_dir / "events.jsonl".
    Callers that need only (session_path, events_path) can unpack:
        session_path, _, _, workspace_dir = resolve_active_session_paths(...)
        events_path = workspace_dir / "events.jsonl"
    """
    resolver = BindingEvidenceResolver(env=dict(env) if env is not None else os.environ)
    evidence = getattr(resolver, "resolve")(mode="user")
    if evidence.config_root is None or evidence.workspaces_home is None:
        raise RuntimeError("binding unavailable")

    workspaces_home = evidence.workspaces_home

    pointer_path = evidence.config_root / "SESSION_STATE.json"
    pointer = parse_session_pointer_document(load_json(pointer_path))
    session_path = resolve_active_session_state_path(pointer, config_root=evidence.config_root)
    fingerprint = str(pointer.get("activeRepoFingerprint") or "").strip()

    if not fingerprint:
        raise RuntimeError("activeRepoFingerprint missing in pointer")

    workspace_dir = workspaces_home / fingerprint

    return session_path, fingerprint, workspaces_home, workspace_dir
