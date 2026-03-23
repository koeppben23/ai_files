"""WI-25 — Tests for governance/infrastructure/governed_archive.py

Tests covering the governed_archive_active_run() wrapper that combines
archive_active_run() with the governance pipeline.
Happy / Edge / Corner / Bad coverage.
All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_runtime.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeState,
)
from governance_runtime.infrastructure.governed_archive import (
    GovernedArchiveResult,
    governed_archive_active_run,
)
from governance_runtime.infrastructure.work_run_archive import WorkRunArchiveResult
from governance_runtime.infrastructure.workspace_paths import run_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"
_OBSERVED_AT = "2026-01-01T12:00:00Z"


def _minimal_session_state_document() -> dict:
    """Create a minimal valid session state document."""
    return {
        "SESSION_STATE": {
            "Phase": "6",
            "phase": "6",
            "Next": "",
            "Mode": "IN_PROGRESS",
            "status": "OK",
            "active_gate": "",
            "session_run_id": "",
        }
    }


def _setup_workspace(tmp_path: Path) -> Path:
    """Set up a minimal workspace with governance-records structure."""
    workspaces_home = tmp_path / "workspaces"
    workspaces_home.mkdir()
    workspace = workspaces_home / _FINGERPRINT
    workspace.mkdir()
    return workspaces_home


def _write_json_atomic(path: Path, payload) -> None:
    """Simple test writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")


# ===================================================================
# Happy path
# ===================================================================


class TestGovernedArchiveHappy:
    """Happy: governed archive runs successfully."""

    def test_returns_governed_archive_result(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-happy-001"

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
        )

        assert isinstance(result, GovernedArchiveResult)
        assert isinstance(result.archive, WorkRunArchiveResult)
        assert result.archive.run_id == run_id

    def test_governance_executes_after_archive(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-happy-002"

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
        )

        assert result.governance.executed is True

    def test_governance_summary_written_to_archive(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-happy-003"

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
        )

        archive_path = run_dir(workspaces_home, _FINGERPRINT, run_id)
        summary_file = archive_path / "governance-summary.json"
        assert summary_file.is_file()
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["schema"] == "governance.governance-summary.v1"

    def test_result_is_frozen(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-happy-004"

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
        )

        with pytest.raises(AttributeError):
            result.archive = None  # type: ignore[misc]


# ===================================================================
# Edge cases
# ===================================================================


class TestGovernedArchiveEdge:
    """Edge: governed archive with various configurations."""

    def test_with_events_path(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-edge-001"
        events_path = tmp_path / "events.jsonl"

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
            events_path=events_path,
        )

        assert result.governance.executed is True
        if events_path.is_file():
            content = events_path.read_text(encoding="utf-8").strip()
            assert len(content) > 0

    def test_with_regulated_mode_config(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-edge-002"

        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            customer_id="CUST-001",
            compliance_framework="DATEV",
            activated_at="2025-01-01T00:00:00Z",
            activated_by="admin",
            minimum_retention_days=3650,
        )

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
            regulated_mode_config=config,
        )

        assert result.governance.executed is True

    def test_with_explicit_workspace_root(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-edge-003"
        workspace_root = workspaces_home / _FINGERPRINT

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
            workspace_root=workspace_root,
        )

        assert result.governance.executed is True


# ===================================================================
# Corner cases
# ===================================================================


class TestGovernedArchiveCorner:
    """Corner: unusual but valid inputs."""

    def test_archive_with_pr_run_type(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-corner-001"

        state = _minimal_session_state_document()["SESSION_STATE"]
        state["PullRequestTitle"] = "Add feature X"
        state["PullRequestBody"] = "Implements feature X for customer Y"
        doc = {"SESSION_STATE": state}

        result = governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=doc,
            state_view=state,
            write_json_atomic=_write_json_atomic,
        )

        assert result.archive.archived_pr_record is True
        assert result.governance.executed is True


# ===================================================================
# Bad path
# ===================================================================


class TestGovernedArchiveBad:
    """Bad: archive failures propagate, governance failures do not."""

    def test_archive_failure_propagates(self, tmp_path: Path):
        workspaces_home = _setup_workspace(tmp_path)
        run_id = "run-bad-001"

        # First create a valid archive to occupy the slot
        governed_archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id=run_id,
            observed_at=_OBSERVED_AT,
            session_state_document=_minimal_session_state_document(),
            state_view=_minimal_session_state_document()["SESSION_STATE"],
            write_json_atomic=_write_json_atomic,
        )

        # Second archive with same run_id should raise (archive already exists)
        with pytest.raises(RuntimeError, match="run archive already exists"):
            governed_archive_active_run(
                workspaces_home=workspaces_home,
                repo_fingerprint=_FINGERPRINT,
                run_id=run_id,
                observed_at=_OBSERVED_AT,
                session_state_document=_minimal_session_state_document(),
                state_view=_minimal_session_state_document()["SESSION_STATE"],
                write_json_atomic=_write_json_atomic,
            )
