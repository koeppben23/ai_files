"""Session state repository and migration scaffold for Wave B.

This module provides deterministic load/save helpers and a fail-closed migration
stub. The migration path is intentionally conservative: only current-version
documents are accepted; older/newer versions are blocked until explicit
migrations are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from governance.engine.reason_codes import BLOCKED_STATE_OUTDATED, REASON_CODE_NONE

CURRENT_SESSION_STATE_VERSION = 1


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
        return payload

    def save(self, document: dict[str, Any]) -> None:
        """Persist one JSON document in deterministic formatting."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(document, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


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
