"""Session state repository and migration scaffold for Wave B.

This module provides deterministic load/save helpers and a fail-closed migration
stub. The migration path is intentionally conservative: only current-version
documents are accepted; older/newer versions are blocked until explicit
migrations are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from governance.engine.reason_codes import BLOCKED_STATE_OUTDATED, REASON_CODE_NONE

CURRENT_SESSION_STATE_VERSION = 1
ATOMIC_REPLACE_RETRIES = 3
ATOMIC_RETRY_DELAY_SECONDS = 0.05


@dataclass(frozen=True)
class SessionStateMigrationResult:
    """Migration outcome for one session-state document."""

    success: bool
    reason_code: str
    document: dict[str, Any]
    detail: str


class SessionStateRepository:
    """Typed repository wrapper for repo-scoped SESSION_STATE documents."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any] | None:
        """Load a JSON document, returning None when the file is absent."""

        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("session state payload must be a JSON object")
        return _normalize_dual_read_aliases(payload)

    def save(self, document: dict[str, Any]) -> None:
        """Persist one JSON document in deterministic formatting.

        Writes are atomic within the same filesystem:
        temp file -> fsync -> os.replace(final).
        """

        self.path.parent.mkdir(parents=True, exist_ok=True)
        canonical = _canonicalize_for_write(document)
        payload = json.dumps(canonical, indent=2, ensure_ascii=True) + "\n"
        _atomic_write_text(self.path, payload)


def _normalize_dual_read_aliases(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy aliases into canonical fields for phase-1 dual-read."""

    normalized = json.loads(json.dumps(document))
    state = normalized.get("SESSION_STATE")
    if not isinstance(state, dict):
        return normalized

    repo_model = state.get("RepoModel")
    if "RepoMapDigest" not in state and isinstance(repo_model, dict):
        state["RepoMapDigest"] = json.loads(json.dumps(repo_model))

    if "FastPathEvaluation" not in state:
        legacy_fast_path = state.get("FastPath")
        legacy_reason = state.get("FastPathReason")
        if isinstance(legacy_fast_path, bool) or isinstance(legacy_reason, str):
            eligible = bool(legacy_fast_path) if isinstance(legacy_fast_path, bool) else False
            reason = legacy_reason.strip() if isinstance(legacy_reason, str) else "legacy fast path alias"
            state["FastPathEvaluation"] = {
                "Evaluated": True,
                "Eligible": eligible,
                "Applied": eligible,
                "Reason": reason,
                "Preconditions": {},
                "DenyReasons": [] if eligible else ["legacy-alias-without-structured-evidence"],
                "ReducedDiscoveryScope": {"PathsScanned": [], "Skipped": []},
                "EvidenceRefs": [],
            }

    return normalized


def _canonicalize_for_write(document: dict[str, Any]) -> dict[str, Any]:
    """Write canonical session-state payload, dropping legacy aliases."""

    canonical = _normalize_dual_read_aliases(document)
    state = canonical.get("SESSION_STATE")
    if isinstance(state, dict):
        state.pop("RepoModel", None)
        state.pop("FastPath", None)
        state.pop("FastPathReason", None)
    return canonical


def _is_retryable_replace_error(exc: OSError) -> bool:
    """Return True for transient replace failures often seen on Windows."""

    return exc.errno in {errno.EACCES, errno.EPERM, errno.EBUSY}


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync for durability after atomic replace."""

    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)


def _atomic_write_text(path: Path, payload: str) -> None:
    """Atomically write text to `path` with bounded replace retries."""

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
            newline="\n",
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)

        last_error: OSError | None = None
        for attempt in range(ATOMIC_REPLACE_RETRIES):
            try:
                os.replace(str(temp_path), str(path))
                _fsync_directory(path.parent)
                return
            except OSError as exc:
                last_error = exc
                if attempt == ATOMIC_REPLACE_RETRIES - 1 or not _is_retryable_replace_error(exc):
                    raise
                time.sleep(ATOMIC_RETRY_DELAY_SECONDS)

        if last_error is not None:
            raise last_error
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def migrate_session_state_document(
    document: dict[str, Any],
    *,
    target_version: int,
    target_ruleset_hash: str,
) -> SessionStateMigrationResult:
    """Apply deterministic migration checks to one SESSION_STATE document.

    Wave B stub behavior:
    - only supports `session_state_version == target_version`
    - updates `ruleset_hash` deterministically
    - records migration metadata only when a hash update occurs
    - fail-closes with `BLOCKED-STATE-OUTDATED` for unsupported versions
    """

    state = document.get("SESSION_STATE")
    if not isinstance(state, dict):
        return SessionStateMigrationResult(
            success=False,
            reason_code=BLOCKED_STATE_OUTDATED,
            document=document,
            detail="SESSION_STATE object is missing",
        )

    version = state.get("session_state_version")
    if not isinstance(version, int):
        return SessionStateMigrationResult(
            success=False,
            reason_code=BLOCKED_STATE_OUTDATED,
            document=document,
            detail="session_state_version must be an integer",
        )

    if version != target_version:
        return SessionStateMigrationResult(
            success=False,
            reason_code=BLOCKED_STATE_OUTDATED,
            document=document,
            detail=(
                "unsupported session_state_version for deterministic migration stub "
                f"(found={version}, target={target_version})"
            ),
        )

    ruleset_hash = state.get("ruleset_hash")
    if not isinstance(ruleset_hash, str):
        return SessionStateMigrationResult(
            success=False,
            reason_code=BLOCKED_STATE_OUTDATED,
            document=document,
            detail="ruleset_hash must be a string",
        )

    if ruleset_hash == target_ruleset_hash:
        return SessionStateMigrationResult(
            success=True,
            reason_code=REASON_CODE_NONE,
            document=document,
            detail="no migration required",
        )

    migrated = json.loads(json.dumps(document))
    migrated_state = migrated["SESSION_STATE"]
    migrated_state["ruleset_hash"] = target_ruleset_hash
    migrated_state["Migration"] = {
        "fromVersion": version,
        "toVersion": target_version,
        "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rollbackAvailable": True,
    }
    return SessionStateMigrationResult(
        success=True,
        reason_code=REASON_CODE_NONE,
        document=migrated,
        detail="ruleset hash refreshed",
    )
