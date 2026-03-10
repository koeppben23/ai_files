# Record Finalization & Verify Guide

**Version:** 1.1.0-RC.2
**Contract:** AUDIT_STORAGE_CONTRACT.v1
**Last Updated:** 2026-03-10

## Purpose

This document explains when a run archive is considered finalized, what preconditions must be met, how verification works, and what happens on failure.

## Finalization Lifecycle

A run archive transitions through the following statuses:

```
in_progress → materialized → finalized
                           ↘ failed
```

### Materialization

Materialization (`archive_active_run()` in `governance/infrastructure/work_run_archive.py:50-254`) creates a new run archive directory and writes all artifacts:

1. Session state snapshot (`SESSION_STATE.json`)
2. Plan record (if `run_type = "plan"`)
3. PR record (if `run_type = "pr"`)
4. Metadata (`metadata.json`) with digests and status
5. Run manifest (`run-manifest.json`) with lifecycle fields
6. Provenance record (`provenance-record.json`)
7. Checksums (`checksums.json`) — SHA-256 of all written files

At this point, `archive_status = "materialized"` and `run_status = "materialized"`.

### Verification (Pre-Finalization)

After writing all artifacts, `verify_run_archive()` (`governance/infrastructure/io_verify.py:69-402`) performs:

1. **Required file check** — All 5 required files must exist
2. **Checksum schema validation** — `checksums.json` must have correct schema and valid entries
3. **SHA-256 recomputation** — Every file listed in checksums is re-read and its hash compared
4. **Cross-document consistency** — `run_id`, `repo_fingerprint`, and timestamps must match across manifest, metadata, and provenance
5. **Lifecycle invariant check** — Status fields must be consistent per the invariant table
6. **Archived files declaration check** — `archived_files` in metadata must match actual file presence

### Finalization

If verification passes:

1. `run_manifest.json` is updated with `run_status = "finalized"`, `record_status = "finalized"`, `integrity_status = "passed"`, `finalized_at` timestamp
2. `metadata.json` is updated with `archive_status = "finalized"`, `finalization_reason = "all-required-artifacts-present-and-verified"`
3. Checksums are recomputed to include the updated manifest
4. A second `verify_run_archive()` runs to confirm post-finalization integrity

**Source:** `governance/infrastructure/work_run_archive.py:172-194`

### Finalization Invariants

| Field | Finalized | Failed | Materialized |
|---|---|---|---|
| `run_status` | `finalized` | `failed` | `materialized` |
| `record_status` | `finalized` | `invalidated` | — |
| `integrity_status` | `passed` | `failed` | `pending` |
| `finalized_at` | Required (RFC3339 UTC Z) | Forbidden | Forbidden |
| `finalization_errors` | Forbidden (must be null) | Required (non-empty list) | — |

**Source:** `governance/domain/audit_contract.py:133-161` — `LIFECYCLE_INVARIANTS`

## Failure Handling

If any step during materialization or verification fails, the archive enters the failed state:

1. A failure metadata record is written (`archive_status = "failed"`, `failure_reason = <error message>`)
2. A failure manifest is written (`run_status = "failed"`, `record_status = "invalidated"`, `integrity_status = "failed"`, `finalization_errors = [<error>]`)
3. The original exception is re-raised

**Source:** `governance/infrastructure/work_run_archive.py:195-244`

### Failure Categories

The failure model (`governance/domain/failure_model.py`) classifies failures into:

| Category | Example | Default Severity |
|---|---|---|
| `CHECKSUM_MISMATCH` | SHA-256 recomputation fails | `FATAL` |
| `MISSING_ARTIFACT` | Required file not written | `FATAL` |
| `SCHEMA_VIOLATION` | Invalid schema identifier | `ERROR` |
| `CROSS_DOCUMENT_INCONSISTENCY` | Run ID mismatch across documents | `FATAL` |
| `DUPLICATE_ARCHIVE` | Archive slot already occupied | `ERROR` |
| `FINALIZATION_GUARD_FAILURE` | Finalization precondition not met | `FATAL` |
| `IO_ERROR` | Filesystem write failure | `ERROR` |
| `UNKNOWN` | Unrecognized error | `FATAL` |

### Recovery Strategies

| Strategy | Description | When Used |
|---|---|---|
| `RETRY` | Remove failed archive slot, re-attempt | Transient I/O errors |
| `INVALIDATE_PARTIAL` | Mark partial bundle as permanently invalid | Unrecoverable write failures |
| `REBUILD_FROM_FINALIZED` | Reconstruct export from finalized artifacts | Export corruption |
| `ESCALATE` | Require manual intervention | Unknown failures |

**Source:** `governance/domain/failure_model.py` — `RecoveryStrategy`, `FAILURE_CLASSIFICATION_TABLE`

### Failed Archive Retry

Failed archive slots can be retried: `archive_active_run()` detects `run_status = "failed"` on an existing archive slot and removes it before re-attempting.

**Source:** `governance/infrastructure/work_run_archive.py:64-73`

## Duplicate Archive Prevention

If a non-failed archive already exists for a given `run_id`, materialization raises a `RuntimeError`. This prevents accidental overwrites of finalized records.

**Source:** `governance/infrastructure/work_run_archive.py:74-77`

## Related Documentation

- [Audit Architecture Overview](audit-architecture-overview.md)
- [Example: Finalized Audit Bundle](example-finalized-audit-bundle.md)
- [Example: Failed/Invalidated Run](example-failed-invalidated-run.md)
