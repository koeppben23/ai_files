"""WI-13 — Tests for governance/infrastructure/archive_export.py

Comprehensive Happy / Edge / Corner / Bad coverage for:
  - validate_archive_for_export()  (pure — checks directory structure)
  - validate_restored_bundle()     (pure — checks bundle completeness)
  - export_finalized_bundle()      (I/O — copies + manifests)
  - restore_from_bundle()          (I/O — copies from bundle)
  - write_legal_hold_record()      (I/O — persist hold JSON)
  - load_legal_holds()             (I/O — read hold JSONs)

All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.domain.classification import ClassificationLevel
from governance.domain.retention import (
    ArchiveFormat,
    LegalHold,
    LegalHoldStatus,
)
from governance.infrastructure.archive_export import (
    ALL_EXPORT_FILES,
    EXPORT_MANIFEST_SCHEMA,
    LEGAL_HOLD_SCHEMA,
    OPTIONAL_EXPORT_FILES,
    REQUIRED_EXPORT_FILES,
    export_finalized_bundle,
    load_legal_holds,
    restore_from_bundle,
    validate_archive_for_export,
    validate_restored_bundle,
    write_legal_hold_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT = "abc123def456abc123def456"
_RUN_ID = "run-20260101T000000Z"
_EXPORTED_AT = "2026-01-01T12:00:00Z"
_EXPORTED_BY = "test-operator"


def _create_finalized_archive(base: Path) -> Path:
    """Create a minimal valid finalized archive in base/archive."""
    archive_path = base / "archive"
    archive_path.mkdir(parents=True)

    # Required files
    manifest = {"run_status": "finalized", "run_id": _RUN_ID}
    (archive_path / "run-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (archive_path / "SESSION_STATE.json").write_text(
        json.dumps({"phase": 6}), encoding="utf-8"
    )
    (archive_path / "metadata.json").write_text(
        json.dumps({"created_at": _EXPORTED_AT}), encoding="utf-8"
    )
    (archive_path / "provenance-record.json").write_text(
        json.dumps({"provenance": "test"}), encoding="utf-8"
    )
    (archive_path / "ticket-record.json").write_text(
        json.dumps({"schema": "governance.ticket-record.v1"}), encoding="utf-8"
    )
    (archive_path / "review-decision-record.json").write_text(
        json.dumps({"schema": "governance.review-decision-record.v1"}), encoding="utf-8"
    )
    (archive_path / "outcome-record.json").write_text(
        json.dumps({"schema": "governance.outcome-record.v1"}), encoding="utf-8"
    )
    (archive_path / "evidence-index.json").write_text(
        json.dumps({"schema": "governance.evidence-index.v1"}), encoding="utf-8"
    )
    (archive_path / "checksums.json").write_text(
        json.dumps({"files": {}}), encoding="utf-8"
    )

    return archive_path


def _create_finalized_archive_with_optionals(base: Path) -> Path:
    """Create a finalized archive including optional files."""
    archive_path = _create_finalized_archive(base)
    (archive_path / "plan-record.json").write_text(
        json.dumps({"plan": "test"}), encoding="utf-8"
    )
    (archive_path / "pr-record.json").write_text(
        json.dumps({"pr": "test"}), encoding="utf-8"
    )
    (archive_path / "finalization-record.json").write_text(
        json.dumps({"schema": "governance.finalization-record.v1"}), encoding="utf-8"
    )
    return archive_path


def _make_hold(
    hold_id: str = "HOLD-001",
    status: LegalHoldStatus = LegalHoldStatus.ACTIVE,
) -> LegalHold:
    return LegalHold(
        hold_id=hold_id,
        scope_type="repo",
        scope_value=_FINGERPRINT,
        reason="Audit investigation",
        status=status,
        created_at="2026-01-01T00:00:00Z",
        created_by="compliance-officer",
    )


# ===================================================================
# Happy path
# ===================================================================


class TestValidateArchiveForExportHappy:
    """Happy: valid finalized archive passes validation."""

    def test_valid_archive_passes(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is True
        assert errors == []

    def test_valid_archive_with_optionals(self, tmp_path: Path):
        archive = _create_finalized_archive_with_optionals(tmp_path)
        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is True
        assert errors == []


class TestValidateRestoredBundleHappy:
    """Happy: valid bundle passes validation."""

    def test_valid_bundle_passes(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        # Add export manifest to make it a bundle
        (archive / "export-manifest.json").write_text(
            json.dumps({"schema": EXPORT_MANIFEST_SCHEMA}), encoding="utf-8"
        )
        result = validate_restored_bundle(archive)
        assert result.is_valid is True
        assert result.manifest_present is True
        assert result.files_complete is True
        assert result.errors == ()


class TestExportFinalizedBundleHappy:
    """Happy: export produces a valid bundle directory."""

    def test_export_creates_bundle(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        assert export_path.is_dir()
        assert manifest.schema == EXPORT_MANIFEST_SCHEMA
        assert manifest.repo_fingerprint == _FINGERPRINT
        assert manifest.run_id == _RUN_ID
        assert manifest.exported_at == _EXPORTED_AT
        assert manifest.exported_by == _EXPORTED_BY
        assert manifest.redaction_applied is False
        assert manifest.bundle_manifest_hash.startswith("sha256:")

    def test_export_includes_all_required_files(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        for filename in REQUIRED_EXPORT_FILES:
            assert (export_path / filename).is_file(), f"Missing: {filename}"

    def test_export_writes_manifest_json(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        manifest_file = export_path / "export-manifest.json"
        assert manifest_file.is_file()
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert data["schema"] == EXPORT_MANIFEST_SCHEMA
        assert data["repo_fingerprint"] == _FINGERPRINT
        assert str(data.get("bundle_manifest_hash", "")).startswith("sha256:")

    def test_export_includes_optional_files_when_present(self, tmp_path: Path):
        archive = _create_finalized_archive_with_optionals(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        for filename in OPTIONAL_EXPORT_FILES:
            assert (export_path / filename).is_file()
        assert "plan-record.json" in manifest.files_included

    def test_export_with_redaction_applied(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
            apply_redaction=True,
            redaction_max_level=ClassificationLevel.PUBLIC,
        )

        assert manifest.redaction_applied is True
        assert manifest.redaction_max_level == "public"

    def test_export_manifest_is_frozen(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        with pytest.raises(AttributeError):
            manifest.run_id = "changed"  # type: ignore[misc]

    def test_export_sanitizes_secret_like_json_fields(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"
        (archive / "metadata.json").write_text(
            json.dumps(
                {
                    "created_at": _EXPORTED_AT,
                    "api_key": "top-secret-token",
                    "remote": "https://user:password@example.com/repo.git",
                }
            ),
            encoding="utf-8",
        )

        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        exported = json.loads((export_path / "metadata.json").read_text(encoding="utf-8"))
        assert exported["api_key"] == "***"
        assert "***@" in str(exported["remote"])


class TestRestoreFromBundleHappy:
    """Happy: restore from a valid bundle."""

    def test_restore_creates_archive(self, tmp_path: Path):
        # First export
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"
        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        # Then restore
        restore_path = tmp_path / "restored"
        result = restore_from_bundle(
            bundle_path=export_path,
            restore_path=restore_path,
        )

        assert result.is_valid is True
        assert result.files_complete is True
        assert restore_path.is_dir()

    def test_restore_has_all_required_files(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"
        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        restore_path = tmp_path / "restored"
        restore_from_bundle(bundle_path=export_path, restore_path=restore_path)

        for filename in REQUIRED_EXPORT_FILES:
            assert (restore_path / filename).is_file(), f"Missing: {filename}"


class TestWriteLegalHoldRecordHappy:
    """Happy: legal hold records are persisted."""

    def test_write_creates_file(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        hold = _make_hold()

        result_path = write_legal_hold_record(holds_dir=holds_dir, hold=hold)

        assert result_path.is_file()
        assert result_path.name == "hold-HOLD-001.json"

    def test_write_produces_valid_json(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        hold = _make_hold()

        result_path = write_legal_hold_record(holds_dir=holds_dir, hold=hold)

        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data["schema"] == LEGAL_HOLD_SCHEMA
        assert data["hold_id"] == "HOLD-001"
        assert data["status"] == "active"
        assert data["scope_type"] == "repo"

    def test_write_creates_holds_dir(self, tmp_path: Path):
        holds_dir = tmp_path / "nested" / "holds"
        hold = _make_hold()

        write_legal_hold_record(holds_dir=holds_dir, hold=hold)

        assert holds_dir.is_dir()


class TestLoadLegalHoldsHappy:
    """Happy: legal holds are loaded from disk."""

    def test_load_returns_persisted_hold(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        hold = _make_hold()
        write_legal_hold_record(holds_dir=holds_dir, hold=hold)

        loaded = load_legal_holds(holds_dir)

        assert len(loaded) == 1
        assert loaded[0].hold_id == "HOLD-001"
        assert loaded[0].status == LegalHoldStatus.ACTIVE

    def test_load_multiple_holds(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        write_legal_hold_record(
            holds_dir=holds_dir, hold=_make_hold("HOLD-001")
        )
        write_legal_hold_record(
            holds_dir=holds_dir, hold=_make_hold("HOLD-002")
        )

        loaded = load_legal_holds(holds_dir)
        assert len(loaded) == 2
        hold_ids = {h.hold_id for h in loaded}
        assert hold_ids == {"HOLD-001", "HOLD-002"}

    def test_load_released_hold(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        hold = LegalHold(
            hold_id="HOLD-REL",
            scope_type="repo",
            scope_value=_FINGERPRINT,
            reason="Completed audit",
            status=LegalHoldStatus.RELEASED,
            created_at="2026-01-01T00:00:00Z",
            created_by="officer",
            released_at="2026-06-01T00:00:00Z",
            released_by="officer",
        )
        write_legal_hold_record(holds_dir=holds_dir, hold=hold)

        loaded = load_legal_holds(holds_dir)
        assert len(loaded) == 1
        assert loaded[0].status == LegalHoldStatus.RELEASED
        assert loaded[0].released_at == "2026-06-01T00:00:00Z"


# ===================================================================
# Edge cases
# ===================================================================


class TestValidateArchiveForExportEdge:
    """Edge: boundary conditions for archive validation."""

    def test_missing_one_required_file(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "checksums.json").unlink()

        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is False
        assert any("checksums.json" in e for e in errors)

    def test_not_finalized_run_status(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        # Overwrite with non-finalized status
        (archive / "run-manifest.json").write_text(
            json.dumps({"run_status": "active"}), encoding="utf-8"
        )

        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is False
        assert any("finalized" in e for e in errors)

    def test_empty_run_status(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "run-manifest.json").write_text(
            json.dumps({"run_status": ""}), encoding="utf-8"
        )

        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is False

    def test_missing_run_status_key(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "run-manifest.json").write_text(
            json.dumps({"other_key": "value"}), encoding="utf-8"
        )

        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is False


class TestValidateRestoredBundleEdge:
    """Edge: boundary conditions for bundle validation."""

    def test_missing_export_manifest(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        # No export-manifest.json
        result = validate_restored_bundle(archive)
        assert result.is_valid is False
        assert result.manifest_present is False

    def test_missing_one_required_file_in_bundle(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "export-manifest.json").write_text(
            json.dumps({"schema": EXPORT_MANIFEST_SCHEMA}), encoding="utf-8"
        )
        (archive / "metadata.json").unlink()

        result = validate_restored_bundle(archive)
        assert result.is_valid is False
        assert result.files_complete is False


class TestExportFinalizedBundleEdge:
    """Edge: boundary conditions for export."""

    def test_export_format_in_manifest(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
            export_format=ArchiveFormat.DIRECTORY,
        )

        assert manifest.export_format == "directory"

    def test_exported_files_match_manifest(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        # Every file in manifest.files_included should exist on disk
        for filename in manifest.files_included:
            assert (export_path / filename).is_file()

    def test_source_archive_path_in_manifest(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        assert manifest.source_archive_path == str(archive)


class TestLoadLegalHoldsEdge:
    """Edge: boundary conditions for hold loading."""

    def test_empty_holds_dir(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        loaded = load_legal_holds(holds_dir)
        assert loaded == []

    def test_non_hold_files_ignored(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        (holds_dir / "other-file.json").write_text("{}", encoding="utf-8")
        loaded = load_legal_holds(holds_dir)
        assert loaded == []

    def test_holds_sorted_by_filename(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        write_legal_hold_record(
            holds_dir=holds_dir, hold=_make_hold("HOLD-002")
        )
        write_legal_hold_record(
            holds_dir=holds_dir, hold=_make_hold("HOLD-001")
        )

        loaded = load_legal_holds(holds_dir)
        assert loaded[0].hold_id == "HOLD-001"
        assert loaded[1].hold_id == "HOLD-002"


# ===================================================================
# Corner cases
# ===================================================================


class TestExportRestoreRoundtripCorner:
    """Corner: full export → restore roundtrip."""

    def test_roundtrip_preserves_content(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"
        restore_path = tmp_path / "restored"

        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        result = restore_from_bundle(
            bundle_path=export_path, restore_path=restore_path
        )
        assert result.is_valid is True

        # Content should match
        original = json.loads(
            (archive / "run-manifest.json").read_text(encoding="utf-8")
        )
        restored = json.loads(
            (restore_path / "run-manifest.json").read_text(encoding="utf-8")
        )
        assert original == restored

    def test_roundtrip_with_optional_files(self, tmp_path: Path):
        archive = _create_finalized_archive_with_optionals(tmp_path)
        export_path = tmp_path / "export"
        restore_path = tmp_path / "restored"

        export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        restore_from_bundle(
            bundle_path=export_path, restore_path=restore_path
        )

        for filename in OPTIONAL_EXPORT_FILES:
            assert (restore_path / filename).is_file()


class TestLegalHoldRoundtripCorner:
    """Corner: legal hold write → load roundtrip."""

    def test_roundtrip_preserves_all_fields(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        original = LegalHold(
            hold_id="HOLD-RT",
            scope_type="run",
            scope_value="run-123",
            reason="Investigation #42",
            status=LegalHoldStatus.RELEASED,
            created_at="2025-01-01T00:00:00Z",
            created_by="admin",
            released_at="2026-01-01T00:00:00Z",
            released_by="officer",
        )

        write_legal_hold_record(holds_dir=holds_dir, hold=original)
        loaded = load_legal_holds(holds_dir)

        assert len(loaded) == 1
        restored = loaded[0]
        assert restored.hold_id == original.hold_id
        assert restored.scope_type == original.scope_type
        assert restored.scope_value == original.scope_value
        assert restored.reason == original.reason
        assert restored.status == original.status
        assert restored.created_at == original.created_at
        assert restored.created_by == original.created_by
        assert restored.released_at == original.released_at
        assert restored.released_by == original.released_by

    def test_multiple_holds_roundtrip(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        for i in range(5):
            write_legal_hold_record(
                holds_dir=holds_dir, hold=_make_hold(f"HOLD-{i:03d}")
            )

        loaded = load_legal_holds(holds_dir)
        assert len(loaded) == 5
        ids = [h.hold_id for h in loaded]
        assert ids == [f"HOLD-{i:03d}" for i in range(5)]


class TestValidateArchiveCorner:
    """Corner: unusual archive structures."""

    def test_archive_with_extra_files(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "extra-unknown-file.txt").write_text("extra", encoding="utf-8")
        is_valid, errors = validate_archive_for_export(archive)
        # Extra files don't invalidate the archive
        assert is_valid is True
        assert errors == []

    def test_malformed_manifest_json(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "run-manifest.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )
        is_valid, errors = validate_archive_for_export(archive)
        assert is_valid is False
        assert any("Cannot read" in e for e in errors)


class TestExportCorner:
    """Corner: unusual export scenarios."""

    def test_export_checksums_verified_flag(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        assert manifest.checksums_verified is True

    def test_export_files_included_is_tuple(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"

        manifest = export_finalized_bundle(
            archive_path=archive,
            export_path=export_path,
            repo_fingerprint=_FINGERPRINT,
            run_id=_RUN_ID,
            exported_at=_EXPORTED_AT,
            exported_by=_EXPORTED_BY,
        )

        assert isinstance(manifest.files_included, tuple)
        assert len(manifest.files_included) >= len(REQUIRED_EXPORT_FILES)


# ===================================================================
# Bad path / failure cases
# ===================================================================


class TestValidateArchiveForExportBad:
    """Bad: invalid archives fail validation."""

    def test_nonexistent_path(self, tmp_path: Path):
        is_valid, errors = validate_archive_for_export(
            tmp_path / "nonexistent"
        )
        assert is_valid is False
        assert len(errors) == 1
        assert "not a directory" in errors[0]

    def test_file_instead_of_directory(self, tmp_path: Path):
        fake = tmp_path / "fakefile"
        fake.write_text("not a dir", encoding="utf-8")
        is_valid, errors = validate_archive_for_export(fake)
        assert is_valid is False
        assert "not a directory" in errors[0]

    def test_empty_directory(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        is_valid, errors = validate_archive_for_export(empty)
        assert is_valid is False
        # Should report all required files missing
        assert len(errors) >= len(REQUIRED_EXPORT_FILES)


class TestValidateRestoredBundleBad:
    """Bad: invalid bundles fail validation."""

    def test_nonexistent_bundle_path(self, tmp_path: Path):
        result = validate_restored_bundle(tmp_path / "nonexistent")
        assert result.is_valid is False
        assert "not a directory" in result.errors[0]

    def test_empty_bundle_directory(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = validate_restored_bundle(empty)
        assert result.is_valid is False
        assert result.manifest_present is False
        assert result.files_complete is False


class TestExportFinalizedBundleBad:
    """Bad: export refuses invalid inputs."""

    def test_export_refuses_non_finalized_archive(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "run-manifest.json").write_text(
            json.dumps({"run_status": "active"}), encoding="utf-8"
        )
        export_path = tmp_path / "export"

        with pytest.raises(RuntimeError, match="not valid for export"):
            export_finalized_bundle(
                archive_path=archive,
                export_path=export_path,
                repo_fingerprint=_FINGERPRINT,
                run_id=_RUN_ID,
                exported_at=_EXPORTED_AT,
                exported_by=_EXPORTED_BY,
            )

    def test_export_refuses_existing_export_path(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        export_path = tmp_path / "export"
        export_path.mkdir()  # Pre-create so it exists

        with pytest.raises(RuntimeError, match="already exists"):
            export_finalized_bundle(
                archive_path=archive,
                export_path=export_path,
                repo_fingerprint=_FINGERPRINT,
                run_id=_RUN_ID,
                exported_at=_EXPORTED_AT,
                exported_by=_EXPORTED_BY,
            )

    def test_export_refuses_missing_archive(self, tmp_path: Path):
        export_path = tmp_path / "export"

        with pytest.raises(RuntimeError, match="not valid for export"):
            export_finalized_bundle(
                archive_path=tmp_path / "nonexistent",
                export_path=export_path,
                repo_fingerprint=_FINGERPRINT,
                run_id=_RUN_ID,
                exported_at=_EXPORTED_AT,
                exported_by=_EXPORTED_BY,
            )

    def test_export_cleans_up_on_source_validation_failure(self, tmp_path: Path):
        """Export should not leave partial directories after validation failure."""
        export_path = tmp_path / "export"

        with pytest.raises(RuntimeError):
            export_finalized_bundle(
                archive_path=tmp_path / "nonexistent",
                export_path=export_path,
                repo_fingerprint=_FINGERPRINT,
                run_id=_RUN_ID,
                exported_at=_EXPORTED_AT,
                exported_by=_EXPORTED_BY,
            )

        # Export path should not exist (validation failed before mkdir)
        assert not export_path.exists()


class TestRestoreFromBundleBad:
    """Bad: restore refuses invalid inputs."""

    def test_restore_refuses_existing_restore_path(self, tmp_path: Path):
        archive = _create_finalized_archive(tmp_path)
        (archive / "export-manifest.json").write_text(
            json.dumps({"schema": EXPORT_MANIFEST_SCHEMA}), encoding="utf-8"
        )
        restore_path = tmp_path / "restored"
        restore_path.mkdir()  # Pre-create

        with pytest.raises(RuntimeError, match="already exists"):
            restore_from_bundle(
                bundle_path=archive,
                restore_path=restore_path,
            )

    def test_restore_returns_invalid_for_bad_bundle(self, tmp_path: Path):
        empty = tmp_path / "empty_bundle"
        empty.mkdir()

        result = restore_from_bundle(
            bundle_path=empty,
            restore_path=tmp_path / "restored",
        )

        assert result.is_valid is False


class TestLoadLegalHoldsBad:
    """Bad: legal hold loading handles corrupt data."""

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        loaded = load_legal_holds(tmp_path / "nonexistent")
        assert loaded == []

    def test_malformed_json_skipped(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        (holds_dir / "hold-BAD.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )

        loaded = load_legal_holds(holds_dir)
        assert loaded == []

    def test_malformed_json_does_not_block_valid(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        write_legal_hold_record(
            holds_dir=holds_dir, hold=_make_hold("HOLD-GOOD")
        )
        (holds_dir / "hold-BAD.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )

        loaded = load_legal_holds(holds_dir)
        assert len(loaded) == 1
        assert loaded[0].hold_id == "HOLD-GOOD"

    def test_hold_with_invalid_status_skipped(self, tmp_path: Path):
        holds_dir = tmp_path / "holds"
        holds_dir.mkdir()
        record = {
            "schema": LEGAL_HOLD_SCHEMA,
            "hold_id": "HOLD-INVALID",
            "scope_type": "repo",
            "scope_value": _FINGERPRINT,
            "reason": "test",
            "status": "invalid_status_value",
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": "test",
        }
        (holds_dir / "hold-INVALID.json").write_text(
            json.dumps(record), encoding="utf-8"
        )

        loaded = load_legal_holds(holds_dir)
        # Invalid status raises ValueError in LegalHoldStatus() → skipped
        assert loaded == []


# ===================================================================
# Contract invariants
# ===================================================================


class TestArchiveExportContractInvariants:
    """Contract: structural invariants that must always hold."""

    def test_required_files_is_frozenset(self):
        assert isinstance(REQUIRED_EXPORT_FILES, frozenset)

    def test_optional_files_is_frozenset(self):
        assert isinstance(OPTIONAL_EXPORT_FILES, frozenset)

    def test_all_files_is_union(self):
        assert ALL_EXPORT_FILES == REQUIRED_EXPORT_FILES | OPTIONAL_EXPORT_FILES

    def test_required_and_optional_disjoint(self):
        assert REQUIRED_EXPORT_FILES & OPTIONAL_EXPORT_FILES == frozenset()

    def test_session_state_in_required(self):
        assert "SESSION_STATE.json" in REQUIRED_EXPORT_FILES

    def test_manifest_in_required(self):
        assert "run-manifest.json" in REQUIRED_EXPORT_FILES

    def test_checksums_in_required(self):
        assert "checksums.json" in REQUIRED_EXPORT_FILES

    def test_export_manifest_schema_version(self):
        assert EXPORT_MANIFEST_SCHEMA.startswith("governance.")
        assert "v1" in EXPORT_MANIFEST_SCHEMA

    def test_legal_hold_schema_version(self):
        assert LEGAL_HOLD_SCHEMA.startswith("governance.")
        assert "v1" in LEGAL_HOLD_SCHEMA

    def test_all_required_files_are_json(self):
        for f in REQUIRED_EXPORT_FILES:
            assert f.endswith(".json"), f"{f} is not a JSON file"
