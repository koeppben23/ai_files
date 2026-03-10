# Example: Failed/Invalidated Run

**Version:** 1.1.0-RC.2
**Last Updated:** 2026-03-10

## Purpose

This document provides an annotated example of a failed run archive showing the failure reason, finalization errors, and invalidated state. It demonstrates what a regulated auditor would see when examining a failing audit record.

## Scenario

During materialization, the checksum verification step detected a mismatch — a file was corrupted or tampered with between write and verification.

## Directory Structure

```
governance-records/<fingerprint>/runs/<run-id>/
  SESSION_STATE.json          (may be incomplete)
  metadata.json               (failure metadata)
  run-manifest.json           (failure manifest)
```

Note: A failed archive may have fewer files than a finalized one. The failure handler writes metadata and manifest to document the failure, but other artifacts may be missing or incomplete.

## Artifact Contents

### run-manifest.json (Failed)

```json
{
  "schema": "governance.run-manifest.v1",
  "repo_fingerprint": "abc123def456abc123def456",
  "run_id": "run-20260310-002",
  "run_type": "analysis",
  "materialized_at": "2026-03-10T15:00:00Z",
  "source_phase": "4",
  "source_active_gate": "",
  "source_next": "5",
  "run_status": "failed",
  "record_status": "invalidated",
  "finalized_at": null,
  "integrity_status": "failed",
  "required_artifacts": {
    "session_state": true,
    "run_manifest": true,
    "metadata": true,
    "provenance": true,
    "plan_record": false,
    "pr_record": false,
    "checksums": true
  },
  "finalization_errors": [
    "archive-error:run archive integrity verify failed after metadata finalization: checksum mismatch for SESSION_STATE.json"
  ]
}
```

**Key observations:**
- `run_status = "failed"` — archive did not finalize successfully
- `record_status = "invalidated"` — this record is not trustworthy
- `integrity_status = "failed"` — checksum verification failed
- `finalized_at = null` — finalization never completed (forbidden for failed runs)
- `finalization_errors` is a non-empty list (required for failed runs)
- The error message is prefixed with `archive-error:` and describes the specific failure

### metadata.json (Failed)

```json
{
  "schema": "governance.work-run.snapshot.v2",
  "repo_fingerprint": "abc123def456abc123def456",
  "run_id": "run-20260310-002",
  "archived_at": "2026-03-10T15:00:00Z",
  "source_phase": "4",
  "source_active_gate": "",
  "source_next": "5",
  "snapshot_digest": "",
  "snapshot_digest_scope": "session_state",
  "archived_files": {
    "session_state": false,
    "plan_record": false,
    "pr_record": false
  },
  "archive_status": "failed",
  "failure_reason": "run archive integrity verify failed after metadata finalization: checksum mismatch for SESSION_STATE.json"
}
```

**Key observations:**
- `archive_status = "failed"` with explicit `failure_reason`
- `snapshot_digest` is empty — the state could not be reliably captured
- `archived_files` all marked `false` — no files were reliably written
- The failure handler in `work_run_archive.py:195-244` writes this as a best-effort record

## Lifecycle Invariant Compliance

Even in the failed state, the invariant table is satisfied:

| Invariant | Expected | Actual | Pass? |
|---|---|---|---|
| `run_status` | `failed` | `failed` | Yes |
| `record_status` | `invalidated` | `invalidated` | Yes |
| `integrity_status` | `failed` | `failed` | Yes |
| `finalized_at` | Forbidden (null) | `null` | Yes |
| `finalization_errors` | Required (non-empty) | Present | Yes |

**Source:** `governance/domain/audit_contract.py:143-151` — Failed invariant

## Failure Classification

Using the failure model (`governance/domain/failure_model.py`), this failure classifies as:

| Field | Value |
|---|---|
| Category | `CHECKSUM_MISMATCH` |
| Severity | `FATAL` |
| Recovery Strategy | `RETRY` |
| Description | SHA-256 recomputation detected content mismatch |

**Source:** `governance/domain/failure_model.py` — `FAILURE_CLASSIFICATION_TABLE`

## Recovery

### Retry

The failed archive slot can be retried. When `archive_active_run()` encounters an existing archive with `run_status = "failed"`, it removes the failed directory and re-attempts materialization.

**Source:** `governance/infrastructure/work_run_archive.py:64-73`

### Non-Retry

If the failure persists after retry:
- The failed archive remains as evidence of the failure
- The `failure_reason` and `finalization_errors` document what went wrong
- An operator or compliance officer reviews the failure report

## What an Auditor Confirms

1. **Failure is documented:** `failure_reason` and `finalization_errors` explain what happened
2. **Record is invalidated:** `record_status = "invalidated"` prevents this record from being treated as authoritative
3. **No false finalization:** `finalized_at` is null, `integrity_status = "failed"` — the system did not falsely claim success
4. **Fail-closed behavior:** The system refused to finalize an archive that did not pass verification

## Related Documentation

- [Record Finalization & Verify Guide](record-finalization-verify-guide.md)
- [Example: Finalized Audit Bundle](example-finalized-audit-bundle.md)
- [Audit Architecture Overview](audit-architecture-overview.md)
