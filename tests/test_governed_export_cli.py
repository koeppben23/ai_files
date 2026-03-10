"""WI-26 — Tests for governance/entrypoints/governed_export_cli.py

Tests covering the governance-gated export CLI entrypoint.
Happy / Edge / Corner / Bad coverage.
All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.entrypoints.governed_export_cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"
_RUN_ID = "run-20260101T000000Z"
_OBSERVED_AT = "2026-01-01T12:00:00Z"


def _create_finalized_archive(base: Path, run_id: str = _RUN_ID) -> Path:
    """Create a minimal valid finalized archive."""
    archive_path = base / run_id
    archive_path.mkdir(parents=True)

    manifest = {
        "schema": "governance.run-manifest.v1",
        "repo_fingerprint": _FINGERPRINT,
        "run_id": run_id,
        "run_type": "analysis",
        "materialized_at": _OBSERVED_AT,
        "source_phase": "6",
        "source_active_gate": "",
        "source_next": "",
        "run_status": "finalized",
        "record_status": "finalized",
        "finalized_at": _OBSERVED_AT,
        "integrity_status": "passed",
        "required_artifacts": {
            "session_state": True,
            "run_manifest": True,
            "metadata": True,
            "provenance": True,
            "plan_record": False,
            "pr_record": False,
            "checksums": True,
        },
    }
    (archive_path / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    metadata = {
        "schema": "governance.work-run.snapshot.v2",
        "repo_fingerprint": _FINGERPRINT,
        "run_id": run_id,
        "archived_at": _OBSERVED_AT,
        "source_phase": "6",
        "source_active_gate": "",
        "source_next": "",
        "snapshot_digest": "abc123",
        "snapshot_digest_scope": "session_state",
        "archive_status": "finalized",
    }
    (archive_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    provenance = {
        "schema": "governance.provenance-record.v1",
        "repo_fingerprint": _FINGERPRINT,
        "run_id": run_id,
        "trigger": "new_work_session_created",
        "policy_fingerprint": "",
        "binding": {"repo_fingerprint": _FINGERPRINT, "session_run_id": run_id},
        "launcher": "governance.entrypoints.new_work_session",
        "timestamps": {"materialized_at": _OBSERVED_AT},
    }
    (archive_path / "provenance-record.json").write_text(json.dumps(provenance), encoding="utf-8")

    (archive_path / "SESSION_STATE.json").write_text(json.dumps({"phase": 6}), encoding="utf-8")
    (archive_path / "checksums.json").write_text(
        json.dumps({"schema": "governance.run-checksums.v1", "files": {}}), encoding="utf-8"
    )

    return archive_path


# ===================================================================
# Happy path
# ===================================================================


class TestGovernedExportCLIHappy:
    """Happy: CLI exports valid archives successfully."""

    def test_export_valid_archive(self, tmp_path: Path, capsys):
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "test@example.com",
        ])

        assert exit_code == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "ok"
        assert payload["reason"] == "governance-export-completed"

    def test_export_creates_output_dir(self, tmp_path: Path, capsys):
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "test@example.com",
        ])

        assert exit_code == 0
        assert export_path.is_dir()

    def test_export_includes_governance_summary(self, tmp_path: Path, capsys):
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "test@example.com",
        ])

        assert exit_code == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["governance_passed"] is True


# ===================================================================
# Edge cases
# ===================================================================


class TestGovernedExportCLIEdge:
    """Edge: CLI with various role and redaction options."""

    def test_export_with_auditor_role_blocked(self, tmp_path: Path, capsys):
        """Auditors do NOT have export_archive permission — only export_redacted.

        The governance pipeline correctly blocks auditor from unredacted export.
        See governance/domain/access_control.py PERMISSIONS table for SSOT.
        """
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "auditor@example.com",
            "--role", "auditor",
        ])

        assert exit_code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "blocked"

    def test_export_with_redaction(self, tmp_path: Path, capsys):
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "test@example.com",
            "--apply-redaction",
            "--redaction-max-level", "public",
        ])

        assert exit_code == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["redaction_applied"] is True


# ===================================================================
# Corner cases
# ===================================================================


class TestGovernedExportCLICorner:
    """Corner: unusual but valid CLI invocations."""

    def test_export_with_workspace_root(self, tmp_path: Path, capsys):
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "test@example.com",
            "--workspace-root", str(workspace_root),
        ])

        assert exit_code == 0


# ===================================================================
# Bad path
# ===================================================================


class TestGovernedExportCLIBad:
    """Bad: CLI handles errors gracefully."""

    def test_nonexistent_archive_path(self, tmp_path: Path, capsys):
        exit_code = main([
            "--archive-path", str(tmp_path / "nonexistent"),
            "--export-path", str(tmp_path / "export"),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "test@example.com",
        ])

        assert exit_code == 2
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "blocked"
        assert payload["reason"] == "archive-path-not-found"

    def test_empty_archive_blocked(self, tmp_path: Path, capsys):
        archive = tmp_path / "empty-archive"
        archive.mkdir()
        export_path = tmp_path / "export" / "empty-run"

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", "empty-run",
            "--exported-by", "test@example.com",
        ])

        assert exit_code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "blocked"
        assert payload["reason"] == "governance-checks-failed"

    def test_readonly_role_blocked_from_export(self, tmp_path: Path, capsys):
        archive = _create_finalized_archive(tmp_path / "archives")
        export_path = tmp_path / "export" / _RUN_ID

        exit_code = main([
            "--archive-path", str(archive),
            "--export-path", str(export_path),
            "--repo-fingerprint", _FINGERPRINT,
            "--run-id", _RUN_ID,
            "--exported-by", "readonly@example.com",
            "--role", "readonly",
        ])

        # readonly role should be denied export access
        assert exit_code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "blocked"
