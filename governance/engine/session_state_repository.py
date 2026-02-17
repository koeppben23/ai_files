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

from governance.engine.canonical_json import canonical_json_clone, canonical_json_hash
from governance.engine.reason_codes import (
    BLOCKED_SESSION_STATE_LEGACY_UNSUPPORTED,
    BLOCKED_STATE_OUTDATED,
    REASON_CODE_NONE,
    WARN_SESSION_STATE_LEGACY_COMPAT_MODE,
)

CURRENT_SESSION_STATE_VERSION = 1
ROLLOUT_PHASE_DUAL_READ = 1
ROLLOUT_PHASE_ENGINE_ONLY = 2
ROLLOUT_PHASE_LEGACY_REMOVED = 3
ATOMIC_REPLACE_RETRIES = 3
ATOMIC_RETRY_DELAY_SECONDS = 0.05
ENV_SESSION_STATE_LEGACY_COMPAT_MODE = "GOVERNANCE_SESSION_STATE_LEGACY_COMPAT_MODE"


@dataclass(frozen=True)
class SessionStateMigrationResult:
    """Migration outcome for one session-state document."""

    success: bool
    reason_code: str
    document: dict[str, Any]
    detail: str


@dataclass(frozen=True)
class SessionStateLoadResult:
    """Structured repository load result for deterministic warning propagation."""

    document: dict[str, Any] | None
    warning_reason_code: str
    warning_detail: str


@dataclass(frozen=True)
class SessionStateCompatibilityError(Exception):
    """Fail-closed exception for unsupported legacy SESSION_STATE usage."""

    reason_code: str
    detail: str
    primary_action: str = "Migrate SESSION_STATE to canonical fields."
    next_command: str = "${PYTHON_COMMAND} scripts/migrate_session_state.py --workspace <id>"

    def __str__(self) -> str:
        return f"{self.reason_code}: {self.detail}"


class SessionStateRepository:
    """Typed repository wrapper for repo-scoped SESSION_STATE documents."""

    def __init__(
        self,
        path: Path,
        *,
        rollout_phase: int = ROLLOUT_PHASE_DUAL_READ,
        engine_version: str = "1.1.0",
        legacy_compat_mode: bool | None = None,
    ):
        self.path = path
        self.rollout_phase = rollout_phase
        self.engine_version = engine_version
        self.legacy_compat_mode = (
            _read_legacy_compat_mode_from_env() if legacy_compat_mode is None else legacy_compat_mode
        )
        # Backward-compatible side-channel retained while callers migrate to
        # `load_with_result()`.
        self.last_warning_reason_code = REASON_CODE_NONE
        self.last_atomic_replace_retries = 0

    def load(self) -> dict[str, Any] | None:
        """Load a JSON document, returning None when the file is absent.

        Prefer `load_with_result()` for structured warning propagation.
        """

        result = self.load_with_result()
        self.last_warning_reason_code = result.warning_reason_code
        return result.document

    def load_with_result(self) -> SessionStateLoadResult:
        """Load one document and return structured warning metadata."""

        self.last_warning_reason_code = REASON_CODE_NONE
        if not self.path.exists():
            return SessionStateLoadResult(
                document=None,
                warning_reason_code=REASON_CODE_NONE,
                warning_detail="",
            )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("session state payload must be a JSON object")
        if self.rollout_phase == ROLLOUT_PHASE_DUAL_READ:
            return SessionStateLoadResult(
                document=_normalize_dual_read_aliases(payload),
                warning_reason_code=REASON_CODE_NONE,
                warning_detail="",
            )
        if self.rollout_phase >= ROLLOUT_PHASE_ENGINE_ONLY:
            legacy_fields = _legacy_alias_fields(payload)
            if legacy_fields:
                if self.rollout_phase >= ROLLOUT_PHASE_LEGACY_REMOVED:
                    raise SessionStateCompatibilityError(
                        reason_code=BLOCKED_SESSION_STATE_LEGACY_UNSUPPORTED,
                        detail=(
                            "legacy SESSION_STATE aliases are unsupported in legacy-removed mode "
                            f"(fields={','.join(legacy_fields)})"
                        ),
                        primary_action="Run deterministic SESSION_STATE migration before continuing.",
                        next_command="${PYTHON_COMMAND} scripts/migrate_session_state.py --workspace <id>",
                    )
                if not self.legacy_compat_mode:
                    raise SessionStateCompatibilityError(
                        reason_code=BLOCKED_SESSION_STATE_LEGACY_UNSUPPORTED,
                        detail=(
                            "legacy SESSION_STATE aliases are unsupported in engine-only mode "
                            f"(fields={','.join(legacy_fields)})"
                        ),
                        primary_action="Enable explicit compatibility mode or migrate SESSION_STATE.",
                        next_command=(
                            f"export {ENV_SESSION_STATE_LEGACY_COMPAT_MODE}=true"
                        ),
                    )
                detail = (
                    "legacy SESSION_STATE aliases accepted in explicit compatibility mode "
                    f"(fields={','.join(legacy_fields)})"
                )
                return SessionStateLoadResult(
                    document=_normalize_dual_read_aliases(payload),
                    warning_reason_code=WARN_SESSION_STATE_LEGACY_COMPAT_MODE,
                    warning_detail=detail,
                )
        return SessionStateLoadResult(
            document=payload,
            warning_reason_code=REASON_CODE_NONE,
            warning_detail="",
        )

    def save(self, document: dict[str, Any], *, now_utc: datetime | None = None) -> None:
        """Persist one JSON document in deterministic formatting.

        Writes are atomic within the same filesystem:
        temp file -> fsync -> os.replace(final).
        """

        self.path.parent.mkdir(parents=True, exist_ok=True)
        canonical, changed = _canonicalize_for_write(document)
        if changed:
            _record_migration_event(canonical, engine_version=self.engine_version, now_utc=now_utc)
        payload = json.dumps(canonical, indent=2, ensure_ascii=True) + "\n"
        self.last_atomic_replace_retries = _atomic_write_text(self.path, payload)


def session_state_hash(document: dict[str, Any]) -> str:
    """Compute canonical session-state hash independent from legacy alias forms."""

    canonical, _ = _canonicalize_for_write(document)
    return canonical_json_hash(canonical)


def _normalize_dual_read_aliases(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy aliases into canonical fields for phase-1 dual-read."""

    normalized = canonical_json_clone(document)
    state = normalized.get("SESSION_STATE")
    if not isinstance(state, dict):
        return normalized

    repo_model = state.get("RepoModel")
    if "RepoMapDigest" not in state and isinstance(repo_model, dict):
            state["RepoMapDigest"] = canonical_json_clone(repo_model)

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


def _legacy_alias_fields(document: dict[str, Any]) -> tuple[str, ...]:
    """Return legacy alias field names present in deterministic order."""

    state = document.get("SESSION_STATE")
    if not isinstance(state, dict):
        return ()
    fields: list[str] = []
    for key in ("RepoModel", "FastPath", "FastPathReason"):
        if key in state:
            fields.append(key)
    return tuple(fields)


def _read_legacy_compat_mode_from_env() -> bool:
    """Read phase-2 legacy compatibility switch from environment."""

    raw = os.getenv(ENV_SESSION_STATE_LEGACY_COMPAT_MODE)
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"invalid {ENV_SESSION_STATE_LEGACY_COMPAT_MODE} value: {raw!r}; expected true/false"
    )


def _canonicalize_for_write(document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Write canonical session-state payload, dropping legacy aliases.

    Returns `(canonical_document, changed)` where `changed` indicates whether any
    legacy alias conversion/removal occurred.
    """

    canonical = _normalize_dual_read_aliases(document)
    changed = False
    state = canonical.get("SESSION_STATE")
    if isinstance(state, dict):
        if "RepoModel" in state:
            changed = True
        if "FastPath" in state:
            changed = True
        if "FastPathReason" in state:
            changed = True
        state.pop("RepoModel", None)
        state.pop("FastPath", None)
        state.pop("FastPathReason", None)
    return canonical, changed


def _record_migration_event(
    document: dict[str, Any], *, engine_version: str, now_utc: datetime | None = None
) -> None:
    """Append deterministic migration event for alias-to-canonical transitions."""

    state = document.get("SESSION_STATE")
    if not isinstance(state, dict):
        return
    event = {
        "type": "legacy_alias_normalization",
        "from_fields": ["RepoModel", "FastPath", "FastPathReason"],
        "to_fields": ["RepoMapDigest", "FastPathEvaluation"],
        "timestamp": (now_utc or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "engine_version": engine_version,
    }
    events = state.get("migration_events")
    if not isinstance(events, list):
        events = []
        state["migration_events"] = events
    events.append(event)


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


def _atomic_write_text(path: Path, payload: str) -> int:
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
                return attempt
            except OSError as exc:
                last_error = exc
                if attempt == ATOMIC_REPLACE_RETRIES - 1 or not _is_retryable_replace_error(exc):
                    raise
                time.sleep(ATOMIC_RETRY_DELAY_SECONDS)

        if last_error is not None:
            raise last_error
        return 0
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def migrate_session_state_document(
    document: dict[str, Any],
    *,
    target_version: int,
    target_ruleset_hash: str,
    now_utc: datetime | None = None,
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

    migrated = canonical_json_clone(document)
    migrated_state = migrated["SESSION_STATE"]
    migrated_state["ruleset_hash"] = target_ruleset_hash
    migrated_state["Migration"] = {
        "fromVersion": version,
        "toVersion": target_version,
        "completedAt": (now_utc or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "rollbackAvailable": True,
    }
    return SessionStateMigrationResult(
        success=True,
        reason_code=REASON_CODE_NONE,
        document=migrated,
        detail="ruleset hash refreshed",
    )
