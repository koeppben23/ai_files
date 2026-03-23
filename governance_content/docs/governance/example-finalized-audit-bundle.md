# Example: Finalized Audit Bundle

**Version:** 1.1.0-RC.2
**Last Updated:** 2026-03-10

## Purpose

This document provides an annotated example of a complete, finalized run archive with all artifacts, demonstrating what a regulated auditor would see when examining a passing audit record.

## Directory Structure

```
governance-records/<fingerprint>/runs/<run-id>/
  SESSION_STATE.json
  metadata.json
  run-manifest.json
  provenance-record.json
  checksums.json
  plan-record.json          (present because run_type = "plan")
```

## Artifact Contents

### run-manifest.json

```json
{
  "schema": "governance.run-manifest.v1",
  "repo_fingerprint": "abc123def456abc123def456",
  "run_id": "run-20260310-001",
  "run_type": "plan",
  "materialized_at": "2026-03-10T14:30:00Z",
  "source_phase": "4",
  "source_active_gate": "plan_approval",
  "source_next": "5",
  "run_status": "finalized",
  "record_status": "finalized",
  "finalized_at": "2026-03-10T14:30:01Z",
  "integrity_status": "passed",
  "required_artifacts": {
    "session_state": true,
    "run_manifest": true,
    "metadata": true,
    "provenance": true,
    "plan_record": true,
    "pr_record": false,
    "checksums": true
  },
  "finalization_errors": null
}
```

**Key observations:**
- `run_status = "finalized"` and `record_status = "finalized"` — lifecycle complete
- `integrity_status = "passed"` — all checksums verified
- `finalized_at` is present (required for finalized runs)
- `finalization_errors` is null (forbidden for finalized runs)
- `plan_record = true` in `required_artifacts` because `run_type = "plan"`
- `pr_record = false` because this is not a PR run

### metadata.json

```json
{
  "schema": "governance.work-run.snapshot.v2",
  "repo_fingerprint": "abc123def456abc123def456",
  "run_id": "run-20260310-001",
  "archived_at": "2026-03-10T14:30:00Z",
  "source_phase": "4",
  "source_active_gate": "plan_approval",
  "source_next": "5",
  "snapshot_digest": "sha256:a1b2c3d4e5f6...",
  "snapshot_digest_scope": "session_state",
  "ticket_digest": "sha256:...",
  "task_digest": null,
  "plan_record_digest": "sha256:...",
  "impl_digest": null,
  "archived_files": {
    "session_state": true,
    "plan_record": true,
    "pr_record": false,
    "run_manifest": true,
    "provenance_record": true,
    "checksums": true
  },
  "archive_status": "finalized",
  "finalization_reason": "all-required-artifacts-present-and-verified"
}
```

**Key observations:**
- `archive_status = "finalized"` with `finalization_reason` documenting why
- `archived_files` map declares which files are actually present
- `snapshot_digest` provides the content hash of the session state
- Timestamps match across metadata and manifest (`archived_at` = `materialized_at`)

### provenance-record.json

```json
{
  "schema": "governance.provenance-record.v1",
  "repo_fingerprint": "abc123def456abc123def456",
  "run_id": "run-20260310-001",
  "trigger": "session_created",
  "policy_fingerprint": "sha256:...",
  "binding": "opencode",
  "launcher": "governance_runtime.entrypoints.session_reader",
  "timestamps": {
    "materialized_at": "2026-03-10T14:30:00Z"
  }
}
```

**Key observations:**
- `trigger` documents what initiated the run
- `policy_fingerprint` links to the active governance policy at materialization time
- `binding` and `launcher` identify the execution context
- `materialized_at` matches the manifest and metadata timestamps

### checksums.json

```json
{
  "schema": "governance.run-checksums.v1",
  "algorithm": "sha256",
  "entries": {
    "SESSION_STATE.json": "sha256:<64hex>",
    "metadata.json": "sha256:<64hex>",
    "run-manifest.json": "sha256:<64hex>",
    "provenance-record.json": "sha256:<64hex>",
    "plan-record.json": "sha256:<64hex>"
  }
}
```

**Key observations:**
- Every file in the archive has a SHA-256 checksum entry
- `verify_run_archive()` recomputes each hash from the file content and compares
- Any mismatch causes verification to fail and the run to be marked as `failed`

## Verification Outcome

Running `verify_run_archive()` on this archive returns:

```
(True, {}, "")
```

Meaning: integrity passed, no errors, no error message.

**Source:** `governance/infrastructure/io_verify.py:69-402`

## What an Auditor Confirms

1. **Completeness:** All required files present per run type
2. **Integrity:** Checksums match file contents
3. **Consistency:** run_id, repo_fingerprint, timestamps agree across all documents
4. **Lifecycle:** Status fields follow the invariant table
5. **Provenance:** Who/what/when is recorded and verifiable

## Related Documentation

- [Record Finalization & Verify Guide](record-finalization-verify-guide.md)
- [Example: Failed/Invalidated Run](example-failed-invalidated-run.md)
- [Audit Architecture Overview](audit-architecture-overview.md)
