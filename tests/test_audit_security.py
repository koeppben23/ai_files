"""Audit Security Tests — WI-3 Test Matrix Hardening.

Tests security properties of the audit infrastructure:
- Path traversal prevention
- Artifact tampering detection
- Checksum integrity enforcement
- Schema poisoning resistance
- Fail-closed behavior on malformed input
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.work_run_archive import archive_active_run
from governance.domain.audit_contract import (
    validate_repo_fingerprint,
    validate_timestamp,
    validate_checksum_digest,
    REQUIRED_ARCHIVE_FILES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"


def _archive_minimal_run(tmp_path: Path, run_id: str = "run-sec-1") -> Path:
    """Create a minimal finalized run archive and return the run root."""
    workspaces_home = tmp_path / "workspaces"
    state = {
        "session_run_id": run_id,
        "Phase": "4",
        "active_gate": "Ticket Input Gate",
        "Next": "5",
    }
    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=_FINGERPRINT,
        run_id=run_id,
        observed_at="2026-03-10T10:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )
    return workspaces_home / "governance-records" / _FINGERPRINT / "runs" / run_id


# ---------------------------------------------------------------------------
# Path traversal prevention
# ---------------------------------------------------------------------------

class TestPathTraversalPrevention:
    """Ensure archive operations reject path traversal attempts."""

    def test_repo_fingerprint_rejects_traversal(self) -> None:
        violations = validate_repo_fingerprint("../../../etc/passwd")
        assert len(violations) == 1
        assert violations[0].code == "INVALID_REPO_FINGERPRINT"

    def test_repo_fingerprint_rejects_slashes(self) -> None:
        violations = validate_repo_fingerprint("abc123def456abc1/3def456")
        assert len(violations) == 1
        assert violations[0].code == "INVALID_REPO_FINGERPRINT"

    def test_repo_fingerprint_rejects_uppercase(self) -> None:
        violations = validate_repo_fingerprint("ABC123DEF456ABC123DEF456")
        assert len(violations) == 1

    def test_repo_fingerprint_rejects_empty(self) -> None:
        violations = validate_repo_fingerprint("")
        assert len(violations) == 1

    def test_repo_fingerprint_accepts_valid(self) -> None:
        violations = validate_repo_fingerprint(_FINGERPRINT)
        assert violations == []


# ---------------------------------------------------------------------------
# Artifact tampering detection
# ---------------------------------------------------------------------------

class TestArtifactTamperingDetection:
    """Ensure tampered artifacts are detected by verify_run_archive."""

    def test_tampered_session_state_detected(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        # Tamper with SESSION_STATE.json
        state_path = run_root / "SESSION_STATE.json"
        state_path.write_text('{"tampered": true}', encoding="utf-8")

        ok, _, msg = verify_run_archive(run_root)
        assert not ok
        assert msg is not None

    def test_tampered_manifest_detected(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        manifest_path = run_root / "run-manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["run_id"] = "tampered-id"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        ok, _, msg = verify_run_archive(run_root)
        assert not ok

    def test_tampered_provenance_detected(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        prov_path = run_root / "provenance-record.json"
        payload = json.loads(prov_path.read_text(encoding="utf-8"))
        payload["trigger"] = "tampered_trigger"
        prov_path.write_text(json.dumps(payload), encoding="utf-8")

        ok, _, msg = verify_run_archive(run_root)
        assert not ok

    def test_deleted_required_artifact_detected(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        (run_root / "provenance-record.json").unlink()
        ok, _, msg = verify_run_archive(run_root)
        assert not ok
        assert "provenance" in (msg or "").lower() or "missing" in (msg or "").lower()


# ---------------------------------------------------------------------------
# Checksum integrity enforcement
# ---------------------------------------------------------------------------

class TestChecksumIntegrity:
    """Ensure checksum verification is strict."""

    def test_checksum_mismatch_fails_verification(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        checksums_path = run_root / "checksums.json"
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        # Replace a checksum with a fake one
        files = checksums["files"]
        first_key = next(iter(files))
        files[first_key] = "sha256:" + "0" * 64
        checksums_path.write_text(json.dumps(checksums), encoding="utf-8")

        ok, _, msg = verify_run_archive(run_root)
        assert not ok
        assert "checksum" in (msg or "").lower() or "mismatch" in (msg or "").lower()

    def test_valid_archive_passes_checksum_verification(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)
        ok, _, msg = verify_run_archive(run_root)
        assert ok
        assert msg is None


# ---------------------------------------------------------------------------
# Schema poisoning resistance
# ---------------------------------------------------------------------------

class TestSchemaPoisoning:
    """Ensure archives with wrong schema identifiers are rejected."""

    def test_wrong_manifest_schema_rejected(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        manifest_path = run_root / "run-manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["schema"] = "evil.schema.v1"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        # Re-write checksums to match tampered manifest
        checksums_path = run_root / "checksums.json"
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        new_hash = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        checksums["files"]["run-manifest.json"] = new_hash
        checksums_path.write_text(json.dumps(checksums), encoding="utf-8")

        ok, _, msg = verify_run_archive(run_root)
        assert not ok
        assert "schema" in (msg or "").lower()

    def test_wrong_metadata_schema_rejected(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        meta_path = run_root / "metadata.json"
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        payload["schema"] = "evil.metadata.v1"
        meta_path.write_text(json.dumps(payload), encoding="utf-8")

        # Update checksums
        checksums_path = run_root / "checksums.json"
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        new_hash = "sha256:" + hashlib.sha256(meta_path.read_bytes()).hexdigest()
        checksums["files"]["metadata.json"] = new_hash
        checksums_path.write_text(json.dumps(checksums), encoding="utf-8")

        ok, _, msg = verify_run_archive(run_root)
        assert not ok


# ---------------------------------------------------------------------------
# Fail-closed on malformed input
# ---------------------------------------------------------------------------

class TestFailClosed:
    """Ensure the system fails closed on malformed/unexpected input."""

    def test_empty_run_directory_fails(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty-run"
        empty_dir.mkdir()
        ok, _, msg = verify_run_archive(empty_dir)
        assert not ok
        assert "missing" in (msg or "").lower()

    def test_malformed_checksums_json_fails(self, tmp_path: Path) -> None:
        run_root = _archive_minimal_run(tmp_path)

        (run_root / "checksums.json").write_text("not valid json", encoding="utf-8")
        ok, _, msg = verify_run_archive(run_root)
        assert not ok

    def test_invalid_timestamp_contract_validation(self) -> None:
        violations = validate_timestamp("not-a-timestamp", "test_field")
        assert len(violations) == 1
        assert violations[0].code == "INVALID_TIMESTAMP"

    def test_invalid_checksum_format_contract_validation(self) -> None:
        violations = validate_checksum_digest("md5:abcdef", "test_field")
        assert len(violations) == 1
        assert violations[0].code == "INVALID_CHECKSUM_DIGEST"

    def test_valid_timestamp_passes(self) -> None:
        violations = validate_timestamp("2026-03-10T10:00:00Z", "test_field")
        assert violations == []

    def test_valid_checksum_passes(self) -> None:
        digest = "sha256:" + "a" * 64
        violations = validate_checksum_digest(digest, "test_field")
        assert violations == []


# ---------------------------------------------------------------------------
# Duplicate archive prevention
# ---------------------------------------------------------------------------

class TestDuplicateArchivePrevention:
    """Ensure duplicate non-failed archives are rejected."""

    def test_duplicate_finalized_archive_raises(self, tmp_path: Path) -> None:
        workspaces_home = tmp_path / "workspaces"
        state = {
            "session_run_id": "run-dup",
            "Phase": "4",
            "active_gate": "Ticket Input Gate",
            "Next": "5",
        }
        archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=_FINGERPRINT,
            run_id="run-dup",
            observed_at="2026-03-10T10:00:00Z",
            session_state_document={"SESSION_STATE": state},
            state_view=state,
        )

        with pytest.raises(RuntimeError, match="already exists"):
            archive_active_run(
                workspaces_home=workspaces_home,
                repo_fingerprint=_FINGERPRINT,
                run_id="run-dup",
                observed_at="2026-03-10T10:01:00Z",
                session_state_document={"SESSION_STATE": state},
                state_view=state,
            )
