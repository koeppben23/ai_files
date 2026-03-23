"""Tests for PlanRecordRepository lifecycle management.

Covers: load, append_version, finalize, rotate_to_archive,
backfill_from_session_state, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from artifacts.writers.plan_record import compute_content_hash
from governance_runtime.infrastructure.plan_record_repository import (
    PlanRecordFinalizeResult,
    PlanRecordRepository,
    PlanRecordRotateResult,
    PlanRecordWriteResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FP = "a" * 24  # canonical repo fingerprint


@pytest.fixture()
def repo(tmp_path: Path) -> PlanRecordRepository:
    """Fresh PlanRecordRepository rooted at a temp directory."""
    return PlanRecordRepository(
        path=tmp_path / "plan-record.json",
        archive_dir=tmp_path / "plan-record-archive",
    )


def _version_data(*, trigger: str = "initial") -> dict:
    """Minimal PlanVersion payload (no version/supersedes/content_hash -- repo handles those)."""
    return {
        "timestamp": "2026-03-01T12:00:00+00:00",
        "phase": "4",
        "session_run_id": "sess-001",
        "trigger": trigger,
        "feature_complexity": {
            "class": "COMPLEX",
            "reason": "test reason",
            "planning_depth": "full",
        },
        "ticket_record": {
            "context": "ctx",
            "decision": "dec",
            "rationale": "rat",
            "consequences": "con",
            "rollback": "rb",
        },
        "nfr_checklist": {
            "security_privacy": {"status": "N/A", "detail": "n/a"},
            "observability": {"status": "OK", "detail": "ok"},
            "performance": {"status": "OK", "detail": "ok"},
            "migration_compatibility": {"status": "N/A", "detail": "n/a"},
            "rollback_release_safety": {"status": "OK", "detail": "ok"},
        },
        "test_strategy": ["Unit tests"],
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestLoad:

    def test_load_returns_none_when_missing(self, repo: PlanRecordRepository) -> None:
        assert repo.load() is None

    def test_load_reads_existing_file(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        doc = repo.load()
        assert doc is not None
        assert doc["schema_version"] == "1.0.0"

    def test_current_version_none_when_empty(self, repo: PlanRecordRepository) -> None:
        assert repo.current_version() is None

    def test_version_count_zero_when_missing(self, repo: PlanRecordRepository) -> None:
        assert repo.version_count() == 0


# ---------------------------------------------------------------------------
# Append version
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestAppendVersion:

    def test_first_append_creates_file(self, repo: PlanRecordRepository) -> None:
        result = repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        assert result.ok is True
        assert result.version == 1
        assert repo.path.is_file()

    def test_first_version_has_no_supersedes(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        ver = repo.current_version()
        assert ver is not None
        assert ver["supersedes"] is None

    def test_second_version_supersedes_first(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        result = repo.append_version(
            _version_data(trigger="self_review_revision"),
            phase="4",
            mode="user",
            repo_fingerprint=_FP,
        )
        assert result.ok is True
        assert result.version == 2
        ver = repo.current_version()
        assert ver is not None
        assert ver["supersedes"] == 1
        assert ver["version"] == 2

    def test_version_count_increments(self, repo: PlanRecordRepository) -> None:
        for i in range(3):
            repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        assert repo.version_count() == 3

    def test_content_hash_is_set(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        ver = repo.current_version()
        assert ver is not None
        assert ver["content_hash"].startswith("sha256:")

    def test_content_hash_is_correct(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        ver = repo.current_version()
        assert ver is not None
        expected = compute_content_hash(ver)
        assert ver["content_hash"] == expected

    def test_phase_5_allowed(self, repo: PlanRecordRepository) -> None:
        result = repo.append_version(_version_data(), phase="5", mode="user", repo_fingerprint=_FP)
        assert result.ok is True

    def test_phase_5_variant_allowed(self, repo: PlanRecordRepository) -> None:
        result = repo.append_version(_version_data(), phase="5-ImplementationQA", mode="user", repo_fingerprint=_FP)
        assert result.ok is True

    def test_phase_6_blocked_by_policy(self, repo: PlanRecordRepository) -> None:
        result = repo.append_version(_version_data(), phase="6", mode="user", repo_fingerprint=_FP)
        assert result.ok is False
        assert "PERSIST_PHASE_MISMATCH" in result.reason_code

    def test_phase_2_blocked_by_policy(self, repo: PlanRecordRepository) -> None:
        result = repo.append_version(_version_data(), phase="2", mode="user", repo_fingerprint=_FP)
        assert result.ok is False

    def test_json_file_is_valid(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        text = repo.path.read_text(encoding="utf-8")
        doc = json.loads(text)
        assert doc["status"] == "active"
        assert len(doc["versions"]) == 1


# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestFinalize:

    def test_finalize_sets_status(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        result = repo.finalize(session_run_id="sess-fin", phase="6")
        assert result.ok is True
        doc = repo.load()
        assert doc is not None
        assert doc["status"] == "finalized"
        assert doc["finalized_by_session"] == "sess-fin"
        assert doc["finalized_phase"] == "6"
        assert doc["outcome"] == "completed"
        assert doc["finalized_at"] is not None

    def test_finalize_custom_outcome(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        result = repo.finalize(session_run_id="sess-fin", phase="6", outcome="abandoned")
        assert result.ok is True
        doc = repo.load()
        assert doc is not None
        assert doc["outcome"] == "abandoned"

    def test_finalize_fails_when_missing(self, repo: PlanRecordRepository) -> None:
        result = repo.finalize(session_run_id="sess-fin", phase="6")
        assert result.ok is False
        assert "not-found" in result.reason

    def test_finalize_fails_when_already_finalized(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        repo.finalize(session_run_id="sess-fin", phase="6")
        result = repo.finalize(session_run_id="sess-fin-2", phase="6")
        assert result.ok is False
        assert "already-finalized" in result.reason

    def test_finalize_fails_when_no_versions(self, repo: PlanRecordRepository, tmp_path: Path) -> None:
        # Create an empty document manually
        from artifacts.writers.plan_record import new_plan_record_document, render_plan_record
        from governance_runtime.infrastructure.fs_atomic import atomic_write_text

        doc = new_plan_record_document(_FP)
        atomic_write_text(repo.path, render_plan_record(doc))

        result = repo.finalize(session_run_id="sess-fin", phase="6")
        assert result.ok is False
        assert "no-versions" in result.reason


# ---------------------------------------------------------------------------
# Rotate to archive
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRotateToArchive:

    def test_rotate_moves_file(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        repo.finalize(session_run_id="sess-fin", phase="6")
        result = repo.rotate_to_archive()
        assert result.ok is True
        assert result.archive_path is not None
        assert result.archive_path.is_file()
        assert not repo.path.exists()

    def test_archive_file_has_archived_status(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        repo.finalize(session_run_id="sess-fin", phase="6")
        result = repo.rotate_to_archive()
        assert result.archive_path is not None
        archived_doc = json.loads(result.archive_path.read_text(encoding="utf-8"))
        assert archived_doc["status"] == "archived"

    def test_rotate_creates_archive_dir(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        repo.finalize(session_run_id="sess-fin", phase="6")
        assert not repo.archive_dir.exists()
        repo.rotate_to_archive()
        assert repo.archive_dir.is_dir()

    def test_rotate_fails_when_not_finalized(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        result = repo.rotate_to_archive()
        assert result.ok is False
        assert "not-finalized" in result.reason

    def test_rotate_fails_when_missing(self, repo: PlanRecordRepository) -> None:
        result = repo.rotate_to_archive()
        assert result.ok is False
        assert "not-found" in result.reason


# ---------------------------------------------------------------------------
# Auto-rotate on append after finalize
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestAutoRotateOnAppend:

    def test_append_after_finalize_rotates_and_creates_new(self, repo: PlanRecordRepository) -> None:
        # First cycle
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        repo.finalize(session_run_id="sess-fin-1", phase="6")

        # Second cycle -- should auto-rotate
        result = repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        assert result.ok is True
        assert result.version == 1  # New document, version resets

        doc = repo.load()
        assert doc is not None
        assert doc["status"] == "active"
        assert len(doc["versions"]) == 1

        # Archive should contain the finalized document
        assert repo.archive_dir.is_dir()
        archived = list(repo.archive_dir.glob("*.json"))
        assert len(archived) == 1


# ---------------------------------------------------------------------------
# Backfill from SESSION_STATE
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestBackfillFromSessionState:

    def test_backfill_creates_record(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {
                "Class": "COMPLEX",
                "Reason": "Multi-file changes",
                "PlanningDepth": "full",
            },
            "TicketRecordDigest": "**Context:** Adding persistence\n**Decision:** JSON file\n**Rationale:** Simple\n**Consequences:** New file\n**Rollback:** Delete file",
            "NFRChecklist": {
                "Security/Privacy": {"status": "N/A", "detail": "No user data"},
                "Observability": {"status": "OK", "detail": "Logged"},
                "Performance": {"status": "OK", "detail": "Fast"},
                "Migration/Compatibility": {"status": "N/A", "detail": "New"},
                "Rollback/Release safety": {"status": "OK", "detail": "Safe"},
            },
            "TestStrategy": ["Unit tests", "Integration tests"],
            "Phase": "4",
        }
        result = repo.backfill_from_session_state(
            state, repo_fingerprint=_FP, session_run_id="sess-bf"
        )
        assert result.ok is True
        assert result.version == 1

        doc = repo.load()
        assert doc is not None
        assert doc["status"] == "active"
        ver = doc["versions"][0]
        assert ver["trigger"] == "backfill"
        assert ver["version"] == 1
        assert ver["supersedes"] is None
        assert ver["content_hash"].startswith("sha256:")

    def test_backfill_extracts_feature_complexity(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {
                "Class": "MODIFICATION",
                "Reason": "Changes to existing code",
                "PlanningDepth": "standard",
            },
        }
        repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        ver = repo.current_version()
        assert ver is not None
        assert ver["feature_complexity"]["class"] == "MODIFICATION"
        assert ver["feature_complexity"]["reason"] == "Changes to existing code"
        assert ver["feature_complexity"]["planning_depth"] == "standard"

    def test_backfill_parses_ticket_record(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
            "TicketRecordDigest": "Context: Adding persistence layer\nDecision: Use JSON\nRationale: Simple format\nConsequences: New dependency\nRollback: Delete files",
        }
        repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        ver = repo.current_version()
        assert ver is not None
        assert ver["ticket_record"]["context"] == "Adding persistence layer"
        assert ver["ticket_record"]["decision"] == "Use JSON"
        assert ver["ticket_record"]["rationale"] == "Simple format"
        assert ver["ticket_record"]["consequences"] == "New dependency"
        assert ver["ticket_record"]["rollback"] == "Delete files"

    def test_backfill_falls_back_unparsed(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
            "TicketRecordDigest": "Just some freetext without structure",
        }
        repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        ver = repo.current_version()
        assert ver is not None
        # context falls back to first 200 chars of digest
        assert ver["ticket_record"]["context"] == "Just some freetext without structure"
        assert ver["ticket_record"]["decision"] == "backfill-unparsed"

    def test_backfill_skipped_when_record_exists(self, repo: PlanRecordRepository) -> None:
        repo.append_version(_version_data(), phase="4", mode="user", repo_fingerprint=_FP)
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
        }
        result = repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        assert result.ok is False
        assert "already-exists" in result.reason

    def test_backfill_skipped_without_feature_complexity(self, repo: PlanRecordRepository) -> None:
        state: dict = {}
        result = repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        assert result.ok is False
        assert "no-feature-complexity" in result.reason

    def test_backfill_skipped_empty_feature_complexity_class(self, repo: PlanRecordRepository) -> None:
        state = {"FeatureComplexity": {"Class": "", "Reason": "r"}}
        result = repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        assert result.ok is False

    def test_backfill_normalizes_nfr_keys(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
            "NFRChecklist": {
                "SecurityPrivacy": "OK -- No issues",
                "Observability": "N/A",
                "Performance": {"status": "OK", "detail": "Fast"},
                "MigrationCompatibility": "Risk -- Breaking changes",
                "RollbackReleaseSafety": "OK -- Safe rollback",
            },
        }
        repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        ver = repo.current_version()
        assert ver is not None
        nfr = ver["nfr_checklist"]
        assert nfr["security_privacy"]["status"] == "OK"
        assert nfr["security_privacy"]["detail"] == "No issues"
        assert nfr["observability"]["status"] == "N/A"
        assert nfr["performance"]["status"] == "OK"
        assert nfr["migration_compatibility"]["status"] == "Risk"
        assert nfr["rollback_release_safety"]["status"] == "OK"

    def test_backfill_extracts_touched_surface(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
            "TouchedSurface": {
                "FilesPlanned": ["src/foo.py", "src/bar.py"],
                "ContractsPlanned": ["api/v1/users"],
                "SchemaPlanned": [],
            },
        }
        repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        ver = repo.current_version()
        assert ver is not None
        ts = ver["touched_surface"]
        assert ts is not None
        assert ts["files_planned"] == ["src/foo.py", "src/bar.py"]
        assert ts["contracts_planned"] == ["api/v1/users"]

    def test_backfill_extracts_rollback_strategy(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
            "RollbackStrategy": {
                "Type": "feature-flag",
                "Steps": ["Disable flag"],
                "DataMigrationReversible": True,
                "Risk": "Low",
            },
        }
        repo.backfill_from_session_state(state, repo_fingerprint=_FP, session_run_id="sess-bf")
        ver = repo.current_version()
        assert ver is not None
        rs = ver["rollback_strategy"]
        assert rs is not None
        assert rs["type"] == "feature-flag"
        assert rs["data_migration_reversible"] is True

    def test_backfill_uses_custom_timestamp(self, repo: PlanRecordRepository) -> None:
        state = {
            "FeatureComplexity": {"Class": "COMPLEX", "Reason": "r", "PlanningDepth": "full"},
        }
        repo.backfill_from_session_state(
            state,
            repo_fingerprint=_FP,
            session_run_id="sess-bf",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        ver = repo.current_version()
        assert ver is not None
        assert ver["timestamp"] == "2026-01-01T00:00:00+00:00"
