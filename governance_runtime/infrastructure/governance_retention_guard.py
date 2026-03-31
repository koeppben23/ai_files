"""Governance Retention Guard — Retention check before purge operations.

Intercepts purge_runtime_artifacts() calls to enforce retention policy.
When regulated mode is active, archives cannot be purged until retention
periods have expired and no legal holds are active.

Note: The RUNTIME purge in new_work_session.py (purge_runtime_artifacts)
removes transient workspace files (SESSION_STATE, plan-record, etc.) — NOT
archive runs. Archive runs live under governance-records/<fingerprint>/runs/
and are never touched by the runtime purge. This guard provides an additional
safety layer for any future purge operations that might target archives.

Design:
    - Pure guard functions wrapping the retention domain model
    - Can be inserted before any destructive operation on archives
    - Fail-closed: unknown state blocks purge
    - Zero external dependencies (stdlib + governance.domain)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from governance_runtime.domain.retention import (
    DeletionDecision,
    DeletionEvaluation,
    LegalHold,
    LegalHoldStatus,
    evaluate_deletion,
)
from governance_runtime.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    evaluate_mode,
)


# ---------------------------------------------------------------------------
# Guard result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetentionGuardResult:
    """Result of a retention guard check."""
    purge_allowed: bool
    reason: str
    deletion_evaluation: Optional[DeletionEvaluation]
    checked_run_id: str
    checked_repo_fingerprint: str


# ---------------------------------------------------------------------------
# Guard functions
# ---------------------------------------------------------------------------

def check_archive_retention(
    *,
    run_id: str,
    repo_fingerprint: str,
    classification_level: str = "internal",
    archived_at: str,
    compliance_framework: str = "",
    regulated_mode_config: RegulatedModeConfig = DEFAULT_CONFIG,
    legal_holds: Sequence[LegalHold] = (),
) -> RetentionGuardResult:
    """Check whether an archive run may be purged.

    Evaluates retention policy, legal holds, and regulated mode to determine
    whether the archive identified by run_id may be deleted.

    Args:
        run_id: Run identifier of the archive
        repo_fingerprint: Repository fingerprint
        classification_level: Data classification level of the archive
        archived_at: RFC3339 UTC Z timestamp when the archive was created
        compliance_framework: Active compliance framework (e.g. 'DATEV')
        regulated_mode_config: Regulated mode configuration
        legal_holds: Active legal holds to check

    Returns:
        RetentionGuardResult with purge_allowed=True/False
    """
    try:
        days_ago = _days_since(archived_at)
    except (ValueError, TypeError):
        # Fail-closed: cannot parse date → block purge
        return RetentionGuardResult(
            purge_allowed=False,
            reason="Cannot parse archived_at timestamp — fail-closed: purge blocked",
            deletion_evaluation=None,
            checked_run_id=run_id,
            checked_repo_fingerprint=repo_fingerprint,
        )

    regulated_eval = evaluate_mode(regulated_mode_config)

    deletion_eval = evaluate_deletion(
        run_id=run_id,
        repo_fingerprint=repo_fingerprint,
        classification_level=classification_level,
        archived_at_days_ago=days_ago,
        compliance_framework=compliance_framework,
        regulated_mode_active=regulated_eval.is_active,
        regulated_mode_minimum_days=regulated_mode_config.minimum_retention_days,
        legal_holds=legal_holds,
    )

    return RetentionGuardResult(
        purge_allowed=(deletion_eval.decision == DeletionDecision.ALLOWED),
        reason=deletion_eval.reason,
        deletion_evaluation=deletion_eval,
        checked_run_id=run_id,
        checked_repo_fingerprint=repo_fingerprint,
    )


def check_batch_archive_retention(
    *,
    archive_runs: Sequence[dict[str, str]],
    regulated_mode_config: RegulatedModeConfig = DEFAULT_CONFIG,
    legal_holds: Sequence[LegalHold] = (),
) -> list[RetentionGuardResult]:
    """Check retention for a batch of archive runs.

    Each entry in archive_runs must have: run_id, repo_fingerprint,
    classification_level, archived_at. Optional: compliance_framework.

    Returns a list of RetentionGuardResult in the same order.
    """
    results: list[RetentionGuardResult] = []
    for entry in archive_runs:
        result = check_archive_retention(
            run_id=entry.get("run_id", ""),
            repo_fingerprint=entry.get("repo_fingerprint", ""),
            classification_level=entry.get("classification_level", "internal"),
            archived_at=entry.get("archived_at", ""),
            compliance_framework=entry.get("compliance_framework", ""),
            regulated_mode_config=regulated_mode_config,
            legal_holds=legal_holds,
        )
        results.append(result)
    return results


def load_legal_holds_from_dir(holds_dir: Path) -> list[LegalHold]:
    """Load legal hold records from a directory.

    Each JSON file in the directory is expected to be a legal hold record
    with the governance.legal-hold-record.v1 schema. Invalid files are
    silently skipped (fail-open for loading, fail-closed for evaluation).

    Returns a list of parsed LegalHold records.
    """
    holds: list[LegalHold] = []
    if not holds_dir.is_dir():
        return holds

    for path in sorted(holds_dir.iterdir()):
        if not path.is_file() or not path.suffix == ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue

        status_str = str(payload.get("status", "none")).strip().lower()
        try:
            status = LegalHoldStatus(status_str)
        except ValueError:
            status = LegalHoldStatus.NONE

        try:
            hold = LegalHold(
                hold_id=str(payload.get("hold_id", "")),
                scope_type=str(payload.get("scope_type", "")),
                scope_value=str(payload.get("scope_value", "")),
                reason=str(payload.get("reason", "")),
                status=status,
                created_at=str(payload.get("created_at", "")),
                created_by=str(payload.get("created_by", "")),
                released_at=str(payload.get("released_at", "")),
                released_by=str(payload.get("released_by", "")),
            )
            holds.append(hold)
        except (ValueError, TypeError):
            continue

    return holds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_since(iso_timestamp: str) -> int:
    """Calculate the number of whole days since an ISO timestamp."""
    when = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - when
    return max(0, int(delta.total_seconds() // 86400))


__all__ = [
    "RetentionGuardResult",
    "check_archive_retention",
    "check_batch_archive_retention",
    "load_legal_holds_from_dir",
]
