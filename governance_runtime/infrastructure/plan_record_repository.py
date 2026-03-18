"""Plan-record repository with lifecycle management.

Provides CRUD operations, version appending, finalization,
archive rotation, and backfill from SESSION_STATE for the
plan-record.json artifact.

Architecture: follows the WorkspaceMemoryRepository pattern --
policy check via ``can_write()``, I/O via ``atomic_write_text()``.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from artifacts.writers.plan_record import (
    compute_content_hash,
    new_plan_record_document,
    render_plan_record,
    stamp_version,
)
from governance.application.policies.persistence_policy import (
    ARTIFACT_PLAN_RECORD,
    PersistencePolicyInput,
    can_write,
)
from governance_runtime.infrastructure.fs_atomic import atomic_write_text


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanRecordWriteResult:
    ok: bool
    reason_code: str
    reason: str
    version: int | None = None


@dataclass(frozen=True)
class PlanRecordFinalizeResult:
    ok: bool
    reason: str


@dataclass(frozen=True)
class PlanRecordRotateResult:
    ok: bool
    reason: str
    archive_path: Path | None = None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class PlanRecordRepository:
    """Manages the plan-record.json lifecycle for a single workspace."""

    def __init__(self, path: Path, archive_dir: Path) -> None:
        self.path = path
        self.archive_dir = archive_dir

    # -- Read ---------------------------------------------------------------

    def load(self) -> dict[str, Any] | None:
        """Load the plan-record document, or None if it doesn't exist."""
        if not self.path.is_file():
            return None
        text = self.path.read_text(encoding="utf-8")
        return json.loads(text)

    def current_version(self) -> dict[str, Any] | None:
        """Return the latest PlanVersion entry, or None."""
        doc = self.load()
        if doc is None:
            return None
        versions = doc.get("versions", [])
        if not versions:
            return None
        return versions[-1]

    def version_count(self) -> int:
        """Return the number of versions in the plan record."""
        doc = self.load()
        if doc is None:
            return 0
        return len(doc.get("versions", []))

    # -- Write --------------------------------------------------------------

    def append_version(
        self,
        version_data: dict[str, Any],
        *,
        phase: str,
        mode: str,
        repo_fingerprint: str,
    ) -> PlanRecordWriteResult:
        """Append a new plan version to the record.

        Creates the plan-record.json if it doesn't exist.
        Computes and stamps the content_hash automatically.

        Args:
            version_data: PlanVersion dict (without content_hash).
            phase: Current governance phase (for policy check).
            mode: Operating mode (for policy check).
            repo_fingerprint: Canonical 24-hex fingerprint.

        Returns:
            PlanRecordWriteResult with success/failure info.
        """
        decision = can_write(
            PersistencePolicyInput(
                artifact_kind=ARTIFACT_PLAN_RECORD,
                phase=phase,
                mode=mode,
                gate_approved=False,
                business_rules_executed=False,
                explicit_confirmation="",
            )
        )
        if not decision.allowed:
            return PlanRecordWriteResult(False, decision.reason_code, decision.reason)

        doc = self.load()
        if doc is None:
            doc = new_plan_record_document(repo_fingerprint)

        # Rotate if the existing document is finalized
        if doc.get("status") == "finalized":
            rotate_result = self.rotate_to_archive()
            if not rotate_result.ok:
                return PlanRecordWriteResult(False, "ROTATE_FAILED", rotate_result.reason)
            doc = new_plan_record_document(repo_fingerprint)

        versions = doc.get("versions", [])
        next_version_num = len(versions) + 1

        stamped = dict(version_data)
        stamped["version"] = next_version_num
        if next_version_num > 1:
            stamped["supersedes"] = next_version_num - 1
        else:
            stamped.setdefault("supersedes", None)

        stamped = stamp_version(stamped)
        versions.append(stamped)
        doc["versions"] = versions

        payload = render_plan_record(doc)
        atomic_write_text(self.path, payload)
        return PlanRecordWriteResult(True, "none", "ok", version=next_version_num)

    # -- Lifecycle ----------------------------------------------------------

    def finalize(
        self,
        *,
        session_run_id: str,
        phase: str,
        outcome: str = "completed",
    ) -> PlanRecordFinalizeResult:
        """Mark the plan record as finalized.

        Sets status to ``"finalized"`` with metadata. The document
        becomes immutable -- further appends will trigger rotation.

        Args:
            session_run_id: Session that is finalizing.
            phase: Phase at which finalization occurs (typically "6").
            outcome: One of ``completed``, ``abandoned``, ``superseded``.

        Returns:
            PlanRecordFinalizeResult with success/failure info.
        """
        doc = self.load()
        if doc is None:
            return PlanRecordFinalizeResult(False, "plan-record-not-found")

        if doc.get("status") == "finalized":
            return PlanRecordFinalizeResult(False, "already-finalized")

        if not doc.get("versions"):
            return PlanRecordFinalizeResult(False, "no-versions-to-finalize")

        doc["status"] = "finalized"
        doc["finalized_at"] = datetime.now(timezone.utc).isoformat()
        doc["finalized_by_session"] = session_run_id
        doc["finalized_phase"] = phase
        doc["outcome"] = outcome

        payload = render_plan_record(doc)
        atomic_write_text(self.path, payload)
        return PlanRecordFinalizeResult(True, "ok")

    def rotate_to_archive(self) -> PlanRecordRotateResult:
        """Move the current plan-record.json to the archive directory.

        The archived filename is deterministic:
        ``plan-record-<finalized_at>-<session>.json``

        Returns:
            PlanRecordRotateResult with the archive path on success.
        """
        doc = self.load()
        if doc is None:
            return PlanRecordRotateResult(False, "plan-record-not-found")

        if doc.get("status") != "finalized":
            return PlanRecordRotateResult(False, "plan-record-not-finalized")

        # Build archive filename
        finalized_at = doc.get("finalized_at", "unknown")
        session_id = doc.get("finalized_by_session", "unknown")
        # Sanitize for filesystem: replace colons and other problematic chars
        safe_ts = re.sub(r"[:\+]", "-", finalized_at)
        safe_session = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
        archive_name = f"plan-record-{safe_ts}-{safe_session}.json"

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.archive_dir / archive_name

        # Mark as archived before moving
        doc["status"] = "archived"
        payload = render_plan_record(doc)
        atomic_write_text(archive_path, payload)

        # Remove the active file
        self.path.unlink(missing_ok=True)

        return PlanRecordRotateResult(True, "ok", archive_path=archive_path)

    # -- Backfill -----------------------------------------------------------

    def backfill_from_session_state(
        self,
        session_state: Mapping[str, Any],
        *,
        repo_fingerprint: str,
        session_run_id: str,
        timestamp: str | None = None,
    ) -> PlanRecordWriteResult:
        """Create an initial plan record by extracting data from SESSION_STATE.

        Best-effort extraction: if fields are missing, sensible defaults
        are used. The resulting version is tagged with
        ``trigger: "backfill"`` for audit trail transparency.

        Args:
            session_state: The SESSION_STATE root dict.
            repo_fingerprint: Canonical 24-hex fingerprint.
            session_run_id: Current session run ID.
            timestamp: Optional ISO-8601 timestamp (defaults to now).

        Returns:
            PlanRecordWriteResult with success/failure info.
        """
        if self.load() is not None:
            return PlanRecordWriteResult(False, "BACKFILL_SKIPPED", "plan-record-already-exists")

        fc = session_state.get("FeatureComplexity", {})
        if not isinstance(fc, Mapping) or not fc.get("Class"):
            return PlanRecordWriteResult(False, "BACKFILL_SKIPPED", "no-feature-complexity-in-session-state")

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        phase = str(session_state.get("Phase", "4"))

        version_data: dict[str, Any] = {
            "timestamp": ts,
            "phase": phase,
            "session_run_id": session_run_id,
            "trigger": "backfill",
            "feature_complexity": {
                "class": fc.get("Class", "STANDARD"),
                "reason": fc.get("Reason", "backfill-no-reason"),
                "planning_depth": fc.get("PlanningDepth", "standard"),
            },
            "ticket_record": _extract_ticket_record(session_state),
            "nfr_checklist": _extract_nfr_checklist(session_state),
            "test_strategy": _extract_test_strategy(session_state),
            "touched_surface": _extract_touched_surface(session_state),
            "rollback_strategy": _extract_rollback_strategy(session_state),
            "architecture_options": None,
            "mandatory_review_matrix": session_state.get("MandatoryReviewMatrix"),
            "codebase_context_applied": session_state.get("CodebaseContextApplied"),
            "review_feedback_ref": None,
        }

        # Direct write (bypass policy -- backfill is a recovery operation)
        doc = new_plan_record_document(repo_fingerprint)
        stamped = dict(version_data)
        stamped["version"] = 1
        stamped["supersedes"] = None
        stamped = stamp_version(stamped)
        doc["versions"] = [stamped]

        payload = render_plan_record(doc)
        atomic_write_text(self.path, payload)
        return PlanRecordWriteResult(True, "none", "ok", version=1)


# ---------------------------------------------------------------------------
# Backfill extraction helpers
# ---------------------------------------------------------------------------

_TICKET_RECORD_PATTERNS = {
    "context": re.compile(r"\*?\*?Context\*?\*?:\s*(.+)", re.IGNORECASE),
    "decision": re.compile(r"\*?\*?Decision\*?\*?:\s*(.+)", re.IGNORECASE),
    "rationale": re.compile(r"\*?\*?Rationale\*?\*?:\s*(.+)", re.IGNORECASE),
    "consequences": re.compile(r"\*?\*?Consequences\*?\*?:\s*(.+)", re.IGNORECASE),
    "rollback": re.compile(r"\*?\*?Rollback[^:]*\*?\*?:\s*(.+)", re.IGNORECASE),
}


def _extract_ticket_record(state: Mapping[str, Any]) -> dict[str, Any]:
    """Extract ticket record from TicketRecordDigest (best-effort parse)."""
    digest = state.get("TicketRecordDigest", "")
    if not isinstance(digest, str) or not digest.strip():
        return {
            "context": "backfill-no-data",
            "decision": "backfill-unparsed",
            "rationale": "backfill-unparsed",
            "consequences": "backfill-unparsed",
            "rollback": "backfill-unparsed",
            "open_questions": None,
        }

    extracted: dict[str, str] = {}
    for field, pattern in _TICKET_RECORD_PATTERNS.items():
        match = pattern.search(digest)
        if match:
            extracted[field] = match.group(1).strip()

    return {
        "context": extracted.get("context", digest[:200].strip()),
        "decision": extracted.get("decision", "backfill-unparsed"),
        "rationale": extracted.get("rationale", "backfill-unparsed"),
        "consequences": extracted.get("consequences", "backfill-unparsed"),
        "rollback": extracted.get("rollback", "backfill-unparsed"),
        "open_questions": None,
    }


def _make_nfr_item(value: Any) -> dict[str, str]:
    """Normalize an NFR entry to canonical {status, detail} form."""
    if isinstance(value, Mapping):
        status = str(value.get("status", value.get("Status", "N/A")))
        detail = str(value.get("detail", value.get("Detail", "")))
        return {"status": status if status in ("OK", "N/A", "Risk", "Needs decision") else "N/A", "detail": detail}
    if isinstance(value, str):
        # Try to parse "OK -- some detail" or "Risk -- reason"
        for prefix in ("OK", "N/A", "Risk", "Needs decision"):
            if value.startswith(prefix):
                detail = value[len(prefix):].lstrip(" -:").strip()
                return {"status": prefix, "detail": detail or value}
        return {"status": "N/A", "detail": value}
    return {"status": "N/A", "detail": "backfill-no-data"}


_NFR_KEY_MAP = {
    "security_privacy": ("Security/Privacy", "SecurityPrivacy", "security_privacy", "Security"),
    "observability": ("Observability", "observability"),
    "performance": ("Performance", "performance"),
    "migration_compatibility": ("Migration/Compatibility", "MigrationCompatibility", "migration_compatibility", "Migration"),
    "rollback_release_safety": ("Rollback/Release safety", "RollbackReleaseSafety", "rollback_release_safety", "Rollback"),
}


def _extract_nfr_checklist(state: Mapping[str, Any]) -> dict[str, Any]:
    """Extract NFR checklist to canonical form."""
    nfr = state.get("NFRChecklist", {})
    if not isinstance(nfr, Mapping):
        return {k: {"status": "N/A", "detail": "backfill-no-data"} for k in _NFR_KEY_MAP}

    result: dict[str, Any] = {}
    for canonical_key, lookup_keys in _NFR_KEY_MAP.items():
        value = None
        for lk in lookup_keys:
            if lk in nfr:
                value = nfr[lk]
                break
        result[canonical_key] = _make_nfr_item(value) if value is not None else {"status": "N/A", "detail": "backfill-no-data"}
    return result


def _extract_test_strategy(state: Mapping[str, Any]) -> list[str]:
    """Extract test strategy as a list of strings."""
    ts = state.get("TestStrategy", [])
    if isinstance(ts, list):
        return [str(item) for item in ts]
    if isinstance(ts, str):
        return [ts]
    return []


def _extract_touched_surface(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract touched surface data."""
    ts = state.get("TouchedSurface")
    if not isinstance(ts, Mapping):
        return None
    return {
        "files_planned": [str(f) for f in ts.get("FilesPlanned", ts.get("files_planned", []))],
        "contracts_planned": [str(c) for c in ts.get("ContractsPlanned", ts.get("contracts_planned", []))],
        "schema_planned": [str(s) for s in ts.get("SchemaPlanned", ts.get("schema_planned", []))],
    }


def _extract_rollback_strategy(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract rollback strategy data."""
    rs = state.get("RollbackStrategy")
    if not isinstance(rs, Mapping):
        return None
    return {
        "type": str(rs.get("Type", rs.get("type", "unknown"))),
        "steps": [str(s) for s in rs.get("Steps", rs.get("steps", []))],
        "data_migration_reversible": bool(rs.get("DataMigrationReversible", rs.get("data_migration_reversible", False))),
        "risk": str(rs.get("Risk", rs.get("risk", "unknown"))),
    }
