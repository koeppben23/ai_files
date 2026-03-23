"""WI-24 — Tests for governance/infrastructure/governance_retention_guard.py

Tests covering retention guard checks before purge operations.
Happy / Edge / Corner / Bad coverage.
All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governance_runtime.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeState,
)
from governance_runtime.domain.retention import (
    DeletionDecision,
    LegalHold,
    LegalHoldStatus,
)
from governance_runtime.infrastructure.governance_retention_guard import (
    RetentionGuardResult,
    check_archive_retention,
    check_batch_archive_retention,
    load_legal_holds_from_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"
_RUN_ID = "run-20260101T000000Z"


def _iso_days_ago(days: int) -> str:
    """Return an ISO timestamp N days in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


_ACTIVE_REGULATED_CONFIG = RegulatedModeConfig(
    state=RegulatedModeState.ACTIVE,
    customer_id="CUST-001",
    compliance_framework="DATEV",
    activated_at="2025-01-01T00:00:00Z",
    activated_by="compliance-officer",
    minimum_retention_days=3650,
)


# ===================================================================
# Happy path
# ===================================================================


class TestCheckArchiveRetentionHappy:
    """Happy: retention checks allow or block appropriately."""

    def test_old_archive_can_be_purged(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),  # 400 days, public retention = 365
        )
        assert result.purge_allowed is True
        assert result.deletion_evaluation is not None
        assert result.deletion_evaluation.decision == DeletionDecision.ALLOWED

    def test_recent_archive_blocked(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="internal",
            archived_at=_iso_days_ago(30),  # 30 days, internal retention = 1095
        )
        assert result.purge_allowed is False
        assert result.deletion_evaluation is not None
        assert result.deletion_evaluation.decision == DeletionDecision.BLOCKED_RETENTION

    def test_result_is_frozen(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),
        )
        with pytest.raises(AttributeError):
            result.purge_allowed = False  # type: ignore[misc]

    def test_result_contains_run_id_and_fingerprint(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),
        )
        assert result.checked_run_id == _RUN_ID
        assert result.checked_repo_fingerprint == _FINGERPRINT


class TestCheckBatchRetentionHappy:
    """Happy: batch retention checks."""

    def test_batch_with_mixed_results(self):
        runs = [
            {"run_id": "old-run", "repo_fingerprint": _FINGERPRINT,
             "classification_level": "public", "archived_at": _iso_days_ago(400)},
            {"run_id": "new-run", "repo_fingerprint": _FINGERPRINT,
             "classification_level": "internal", "archived_at": _iso_days_ago(30)},
        ]
        results = check_batch_archive_retention(archive_runs=runs)
        assert len(results) == 2
        assert results[0].purge_allowed is True
        assert results[1].purge_allowed is False

    def test_empty_batch(self):
        results = check_batch_archive_retention(archive_runs=[])
        assert results == []


class TestLoadLegalHoldsHappy:
    """Happy: legal hold loading from directory."""

    def test_load_valid_holds(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()

        hold_data = {
            "schema": "governance.legal-hold-record.v1",
            "hold_id": "HOLD-001",
            "scope_type": "repo",
            "scope_value": _FINGERPRINT,
            "reason": "Audit investigation",
            "status": "active",
            "created_at": "2025-01-01T00:00:00Z",
            "created_by": "legal@company.com",
        }
        (holds_dir / "hold-001.json").write_text(json.dumps(hold_data), encoding="utf-8")

        holds = load_legal_holds_from_dir(holds_dir)
        assert len(holds) == 1
        assert holds[0].hold_id == "HOLD-001"
        assert holds[0].status == LegalHoldStatus.ACTIVE

    def test_load_empty_dir(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        holds = load_legal_holds_from_dir(holds_dir)
        assert holds == []


# ===================================================================
# Edge cases
# ===================================================================


class TestCheckArchiveRetentionEdge:
    """Edge: boundary conditions for retention checks."""

    def test_exactly_at_retention_boundary(self):
        # Public retention = 365 days. At exactly 365 days should be blocked
        # (archived_at_days_ago < effective_days => 365 < 365 is False => ALLOWED)
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(365),
        )
        assert result.purge_allowed is True

    def test_one_day_before_retention_expiry(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(364),
        )
        assert result.purge_allowed is False

    def test_framework_override_extends_retention(self):
        # DATEV override = 3650 days, public base = 365
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),
            compliance_framework="DATEV",
        )
        assert result.purge_allowed is False  # DATEV requires 3650 days


class TestRegulatedModeRetentionEdge:
    """Edge: regulated mode retention override."""

    def test_regulated_mode_blocks_recent_archive(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),
            regulated_mode_config=_ACTIVE_REGULATED_CONFIG,
        )
        assert result.purge_allowed is False

    def test_regulated_mode_inactive_allows_old_archive(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),
            regulated_mode_config=DEFAULT_CONFIG,
        )
        assert result.purge_allowed is True


# ===================================================================
# Corner cases
# ===================================================================


class TestCheckArchiveRetentionCorner:
    """Corner: unusual but valid inputs."""

    def test_unknown_classification_defaults_to_max(self):
        # Unknown classification → fail-closed → restricted (3650 days)
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="unknown_level",
            archived_at=_iso_days_ago(400),
        )
        assert result.purge_allowed is False

    def test_empty_compliance_framework(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(400),
            compliance_framework="",
        )
        assert result.purge_allowed is True


class TestLoadLegalHoldsCorner:
    """Corner: unusual legal hold files."""

    def test_non_json_files_skipped(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        (holds_dir / "readme.txt").write_text("not a hold", encoding="utf-8")
        holds = load_legal_holds_from_dir(holds_dir)
        assert holds == []

    def test_multiple_holds_sorted_by_name(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()

        for i in range(3):
            hold_data = {
                "hold_id": f"HOLD-{i:03d}",
                "scope_type": "repo",
                "scope_value": _FINGERPRINT,
                "reason": f"Reason {i}",
                "status": "active",
                "created_at": "2025-01-01T00:00:00Z",
                "created_by": "legal@company.com",
            }
            (holds_dir / f"hold-{i:03d}.json").write_text(json.dumps(hold_data), encoding="utf-8")

        holds = load_legal_holds_from_dir(holds_dir)
        assert len(holds) == 3
        assert holds[0].hold_id == "HOLD-000"
        assert holds[2].hold_id == "HOLD-002"


# ===================================================================
# Bad path
# ===================================================================


class TestCheckArchiveRetentionBad:
    """Bad: invalid inputs handled gracefully."""

    def test_invalid_timestamp_blocks_purge(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at="not-a-timestamp",
        )
        assert result.purge_allowed is False
        assert "Cannot parse" in result.reason

    def test_empty_timestamp_blocks_purge(self):
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at="",
        )
        assert result.purge_allowed is False

    def test_legal_hold_blocks_even_expired_archive(self):
        hold = LegalHold(
            hold_id="HOLD-BLOCK",
            scope_type="run",
            scope_value=_RUN_ID,
            reason="Legal investigation",
            status=LegalHoldStatus.ACTIVE,
            created_at="2025-01-01T00:00:00Z",
            created_by="legal@company.com",
        )
        result = check_archive_retention(
            run_id=_RUN_ID,
            repo_fingerprint=_FINGERPRINT,
            classification_level="public",
            archived_at=_iso_days_ago(5000),  # Way past retention
            legal_holds=(hold,),
        )
        assert result.purge_allowed is False
        assert result.deletion_evaluation is not None
        assert result.deletion_evaluation.decision == DeletionDecision.BLOCKED_LEGAL_HOLD


class TestLoadLegalHoldsBad:
    """Bad: invalid legal hold files."""

    def test_nonexistent_dir(self, tmp_path: Path):
        holds = load_legal_holds_from_dir(tmp_path / "nonexistent")
        assert holds == []

    def test_invalid_json_file_skipped(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        (holds_dir / "bad.json").write_text("not json", encoding="utf-8")
        holds = load_legal_holds_from_dir(holds_dir)
        assert holds == []

    def test_array_root_json_skipped(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        (holds_dir / "bad.json").write_text("[]", encoding="utf-8")
        holds = load_legal_holds_from_dir(holds_dir)
        assert holds == []
