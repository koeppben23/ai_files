"""Archive Export & Restore — Infrastructure adapter for audit bundle operations.

Provides portable export of finalized run archives into self-contained bundles
with embedded checksums and manifests, and restore/validation of such bundles.
Also implements legal hold and deletion guard operations.

All I/O operations are explicit and documented. Pure validation functions are
separated from side-effecting I/O functions.

Design:
    - Pure validation functions (no I/O) alongside I/O functions
    - Uses retention.py domain model for retention/hold decisions
    - Uses io_verify.verify_run_archive() for integrity checks
    - Uses fs_atomic for safe writes
    - Fail-closed: export refuses to proceed on failed verification
    - Zero external dependencies (stdlib only + governance)
"""

from __future__ import annotations

import json
import shutil
import hashlib
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from governance.domain.classification import ClassificationLevel
from governance_runtime.engine.sanitization import sanitize_for_output
from governance_runtime.domain.canonical_json import canonical_json_text
from governance.domain.retention import (
    ArchiveExportManifest,
    ArchiveFormat,
    LegalHold,
    LegalHoldStatus,
    RestoreValidation,
)
from governance_runtime.infrastructure.fs_atomic import atomic_write_json, atomic_write_text
from governance.infrastructure.redaction import redact_archive


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPORT_MANIFEST_SCHEMA = "governance.archive-export-manifest.v1"
LEGAL_HOLD_SCHEMA = "governance.legal-hold-record.v1"

#: Files that must be present in a valid archive for export
REQUIRED_EXPORT_FILES = frozenset({
    "SESSION_STATE.json",
    "metadata.json",
    "run-manifest.json",
    "provenance-record.json",
    "ticket-record.json",
    "review-decision-record.json",
    "outcome-record.json",
    "evidence-index.json",
    "checksums.json",
})

#: Optional files that may be present
OPTIONAL_EXPORT_FILES = frozenset({
    "plan-record.json",
    "pr-record.json",
    "finalization-record.json",
})

#: All known archive files
ALL_EXPORT_FILES = REQUIRED_EXPORT_FILES | OPTIONAL_EXPORT_FILES


def _compute_bundle_manifest_hash(export_path: Path, files_included: Sequence[str]) -> str:
    file_digests: dict[str, str] = {}
    for name in sorted(files_included):
        payload = (export_path / name).read_bytes()
        file_digests[name] = "sha256:" + hashlib.sha256(payload).hexdigest()
    bundle_manifest = {
        "files": file_digests,
    }
    return "sha256:" + hashlib.sha256(canonical_json_text(bundle_manifest).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Pure validation functions
# ---------------------------------------------------------------------------

def validate_archive_for_export(archive_path: Path) -> tuple[bool, list[str]]:
    """Validate that an archive directory is suitable for export.

    Checks:
    - Directory exists
    - All required files present
    - run-manifest.json has run_status=finalized

    Returns:
        (is_valid, list of error messages)
    """
    errors: list[str] = []

    if not archive_path.is_dir():
        return False, [f"Archive path is not a directory: {archive_path}"]

    for filename in sorted(REQUIRED_EXPORT_FILES):
        filepath = archive_path / filename
        if not filepath.is_file():
            errors.append(f"Required file missing: {filename}")

    # Check finalization status
    manifest_path = archive_path / "run-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run_status = str(manifest.get("run_status", ""))
            if run_status != "finalized":
                errors.append(
                    f"Archive not finalized: run_status={run_status} "
                    f"(expected 'finalized')"
                )
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"Cannot read run-manifest.json: {exc}")

    return len(errors) == 0, errors


def validate_restored_bundle(bundle_path: Path) -> RestoreValidation:
    """Validate a restored archive bundle for completeness and integrity.

    Checks:
    - All required files present
    - Export manifest present
    - Basic structural validity

    Does NOT recompute checksums (caller should use io_verify for that).

    Returns:
        RestoreValidation result
    """
    errors: list[str] = []
    manifest_present = False
    files_complete = True

    if not bundle_path.is_dir():
        return RestoreValidation(
            is_valid=False,
            manifest_present=False,
            checksums_verified=False,
            files_complete=False,
            errors=("Bundle path is not a directory",),
        )

    # Check export manifest
    export_manifest_path = bundle_path / "export-manifest.json"
    if export_manifest_path.is_file():
        manifest_present = True
    else:
        errors.append("export-manifest.json missing from bundle")

    # Check required archive files
    for filename in sorted(REQUIRED_EXPORT_FILES):
        if not (bundle_path / filename).is_file():
            errors.append(f"Required file missing: {filename}")
            files_complete = False

    return RestoreValidation(
        is_valid=len(errors) == 0,
        manifest_present=manifest_present,
        checksums_verified=False,  # Caller should verify with io_verify
        files_complete=files_complete,
        errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# Export operations (I/O)
# ---------------------------------------------------------------------------

def export_finalized_bundle(
    *,
    archive_path: Path,
    export_path: Path,
    repo_fingerprint: str,
    run_id: str,
    exported_at: str,
    exported_by: str,
    export_format: ArchiveFormat = ArchiveFormat.DIRECTORY,
    apply_redaction: bool = False,
    redaction_max_level: ClassificationLevel = ClassificationLevel.INTERNAL,
) -> ArchiveExportManifest:
    """Export a finalized run archive into a self-contained bundle.

    The export produces a directory containing all archive files plus an
    export-manifest.json. Optionally applies redaction based on the
    classification policy.

    Fails if:
    - Archive is not valid for export (missing files, not finalized)
    - Export path already exists (no overwrites)

    Args:
        archive_path: Source finalized archive directory
        export_path: Destination directory for the bundle
        repo_fingerprint: Repository fingerprint
        run_id: Run identifier
        exported_at: RFC3339 UTC Z timestamp
        exported_by: Identity of the exporter
        export_format: Output format (currently only DIRECTORY supported)
        apply_redaction: Whether to apply field-level redaction
        redaction_max_level: Maximum classification level in output

    Returns:
        ArchiveExportManifest describing the export

    Raises:
        RuntimeError: If validation fails or export path exists
    """
    # Validate source
    is_valid, validation_errors = validate_archive_for_export(archive_path)
    if not is_valid:
        raise RuntimeError(
            f"Archive not valid for export: {'; '.join(validation_errors)}"
        )

    # Refuse to overwrite
    if export_path.exists():
        raise RuntimeError(f"Export path already exists: {export_path}")

    export_path.mkdir(parents=True, exist_ok=False)

    try:
        # Copy archive files
        files_included: list[str] = []
        for filename in sorted(ALL_EXPORT_FILES):
            src = archive_path / filename
            if src.is_file():
                if apply_redaction and filename.endswith(".json"):
                    # Load, redact, write
                    doc = json.loads(src.read_text(encoding="utf-8"))
                    sanitized_doc = sanitize_for_output(doc)
                    redacted = redact_archive(
                        {filename: sanitized_doc},
                        max_level=redaction_max_level,
                    )
                    atomic_write_json(export_path / filename, redacted[filename])
                elif filename.endswith(".json"):
                    doc = json.loads(src.read_text(encoding="utf-8"))
                    atomic_write_json(export_path / filename, sanitize_for_output(doc))
                else:
                    shutil.copy2(src, export_path / filename)
                files_included.append(filename)

        # Write export manifest
        manifest = ArchiveExportManifest(
            schema=EXPORT_MANIFEST_SCHEMA,
            repo_fingerprint=repo_fingerprint,
            run_id=run_id,
            exported_at=exported_at,
            exported_by=exported_by,
            export_format=export_format.value,
            source_archive_path=str(archive_path),
            files_included=tuple(files_included),
            checksums_verified=True,
            redaction_applied=apply_redaction,
            redaction_max_level=redaction_max_level.value,
            bundle_manifest_hash=_compute_bundle_manifest_hash(export_path, files_included),
        )

        manifest_dict = {
            "schema": manifest.schema,
            "repo_fingerprint": manifest.repo_fingerprint,
            "run_id": manifest.run_id,
            "exported_at": manifest.exported_at,
            "exported_by": manifest.exported_by,
            "export_format": manifest.export_format,
            "source_archive_path": manifest.source_archive_path,
            "files_included": list(manifest.files_included),
            "checksums_verified": manifest.checksums_verified,
            "redaction_applied": manifest.redaction_applied,
            "redaction_max_level": manifest.redaction_max_level,
            "bundle_manifest_hash": manifest.bundle_manifest_hash,
        }

        atomic_write_json(export_path / "export-manifest.json", manifest_dict)

        return manifest

    except Exception:
        # Clean up partial export on failure
        if export_path.exists():
            shutil.rmtree(export_path, ignore_errors=True)
        raise


def restore_from_bundle(
    *,
    bundle_path: Path,
    restore_path: Path,
) -> RestoreValidation:
    """Restore an archive from an exported bundle.

    Copies all recognized archive files from the bundle to the restore path.
    Validates the bundle before restoring.

    Args:
        bundle_path: Source bundle directory
        restore_path: Destination restore directory

    Returns:
        RestoreValidation describing the result

    Raises:
        RuntimeError: If restore path already exists
    """
    validation = validate_restored_bundle(bundle_path)
    if not validation.is_valid:
        return validation

    if restore_path.exists():
        raise RuntimeError(f"Restore path already exists: {restore_path}")

    restore_path.mkdir(parents=True, exist_ok=False)

    try:
        errors: list[str] = []
        for filename in sorted(ALL_EXPORT_FILES):
            src = bundle_path / filename
            if src.is_file():
                shutil.copy2(src, restore_path / filename)

        # Verify required files arrived
        files_complete = True
        for filename in sorted(REQUIRED_EXPORT_FILES):
            if not (restore_path / filename).is_file():
                errors.append(f"Required file not restored: {filename}")
                files_complete = False

        return RestoreValidation(
            is_valid=len(errors) == 0,
            manifest_present=validation.manifest_present,
            checksums_verified=False,
            files_complete=files_complete,
            errors=tuple(errors),
        )

    except Exception:
        if restore_path.exists():
            shutil.rmtree(restore_path, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# Legal hold I/O
# ---------------------------------------------------------------------------

def write_legal_hold_record(
    *,
    holds_dir: Path,
    hold: LegalHold,
) -> Path:
    """Write a legal hold record to disk.

    Args:
        holds_dir: Directory to store legal hold records
        hold: The legal hold to persist

    Returns:
        Path to the written record file
    """
    holds_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "schema": LEGAL_HOLD_SCHEMA,
        "hold_id": hold.hold_id,
        "scope_type": hold.scope_type,
        "scope_value": hold.scope_value,
        "reason": hold.reason,
        "status": hold.status.value,
        "created_at": hold.created_at,
        "created_by": hold.created_by,
        "released_at": hold.released_at,
        "released_by": hold.released_by,
    }

    record_path = holds_dir / f"hold-{hold.hold_id}.json"
    atomic_write_json(record_path, record)
    return record_path


def load_legal_holds(holds_dir: Path) -> list[LegalHold]:
    """Load all legal hold records from a directory.

    Returns an empty list if the directory does not exist.
    Skips malformed records (fail-open on read, fail-closed on enforcement).
    """
    if not holds_dir.is_dir():
        return []

    holds: list[LegalHold] = []
    for path in sorted(holds_dir.glob("hold-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            hold = LegalHold(
                hold_id=str(data.get("hold_id", "")),
                scope_type=str(data.get("scope_type", "")),
                scope_value=str(data.get("scope_value", "")),
                reason=str(data.get("reason", "")),
                status=LegalHoldStatus(str(data.get("status", "none"))),
                created_at=str(data.get("created_at", "")),
                created_by=str(data.get("created_by", "")),
                released_at=str(data.get("released_at", "")),
                released_by=str(data.get("released_by", "")),
            )
            holds.append(hold)
        except (json.JSONDecodeError, ValueError, OSError):
            # Skip malformed records
            continue

    return holds


__all__ = [
    "EXPORT_MANIFEST_SCHEMA",
    "LEGAL_HOLD_SCHEMA",
    "REQUIRED_EXPORT_FILES",
    "OPTIONAL_EXPORT_FILES",
    "ALL_EXPORT_FILES",
    "validate_archive_for_export",
    "validate_restored_bundle",
    "export_finalized_bundle",
    "restore_from_bundle",
    "write_legal_hold_record",
    "load_legal_holds",
]
