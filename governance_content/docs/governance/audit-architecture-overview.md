# Audit Architecture Overview

**Version:** 1.1.0-RC.2
**Contract:** AUDIT_STORAGE_CONTRACT.v1
**Last Updated:** 2026-03-10

## Purpose

This document describes the audit architecture of the ai-files governance system for regulated customer evaluation. It covers the two-plane architecture, artifact catalog, lifecycle states, and verification model.

## Two-Plane Architecture

The governance system separates concerns into two isolated directory planes:

| Plane | Root Path | Purpose |
|---|---|---|
| **Runtime** | `${WORKSPACES_HOME}/<fingerprint>/` | Active session state, derived artifacts, locks |
| **Audit** | `${WORKSPACES_HOME}/governance-records/<fingerprint>/runs/` | Immutable run archives, manifests, checksums |

**Source:** `governance/infrastructure/workspace_paths.py:167-168` — `runs_dir()` vs `workspace_root()`

The runtime plane holds ephemeral, regenerable data (session state, repo cache, decision packs). The audit plane holds finalized, integrity-verified run archives that must not be modified after finalization.

Purge operations (`purge_runtime_artifacts()` in `governance/infrastructure/run_audit_artifacts.py:180-189`) operate exclusively on the runtime plane using an allowlist. They never descend into `governance-records/`.

## Artifact Catalog

Every finalized run archive contains the following files:

### Required Artifacts (always present)

| File | Schema | Description |
|---|---|---|
| `SESSION_STATE.json` | — | Snapshot of session state at materialization |
| `metadata.json` | `governance.work-run.snapshot.v2` | Archive metadata (digests, timestamps, status) |
| `run-manifest.json` | `governance.run-manifest.v1` | Run lifecycle manifest (status, type, artifacts) |
| `provenance-record.json` | `governance.provenance-record.v1` | Who/what/when triggered the run |
| `checksums.json` | `governance.run-checksums.v1` | SHA-256 checksums of all archive files |

### Conditional Artifacts (per run type)

| File | Schema | Required When |
|---|---|---|
| `plan-record.json` | `governance.plan-record.v1` | `run_type = "plan"` |
| `pr-record.json` | — | `run_type = "pr"` |

**Source:** `governance/domain/audit_contract.py:55-67` — `REQUIRED_ARCHIVE_FILES`, `OPTIONAL_ARCHIVE_FILES`

### Repository-Level Artifacts

| File | Schema | Description |
|---|---|---|
| `repository-manifest.json` | `governance.repository-manifest.v1` | One per repository, documents storage topology |

## Lifecycle States

### Run Status Lifecycle

```
in_progress → materialized → finalized
                           ↘ failed
```

| Status | Record Status | Integrity Status | Finalized At | Errors |
|---|---|---|---|---|
| `finalized` | `finalized` | `passed` | Required | Forbidden |
| `failed` | `invalidated` | `failed` | Forbidden | Required |
| `materialized` | — | `pending` | Forbidden | — |

**Source:** `governance/domain/audit_contract.py:133-161` — `LIFECYCLE_INVARIANTS`

### Archive Status Lifecycle

```
materialized → finalized
             ↘ failed
```

**Source:** `governance/infrastructure/work_run_archive.py:50-254` — `archive_active_run()`

## Verification Model

The verify layer (`governance/infrastructure/io_verify.py`, 456 lines) performs:

1. **File completeness** — All required files present per run type
2. **Checksum recomputation** — SHA-256 of each file compared against `checksums.json`
3. **Cross-document consistency** — `run_id`, `repo_fingerprint`, timestamps match across manifest, metadata, and provenance
4. **Schema validation** — Each artifact's `schema` field matches expected identifier
5. **Lifecycle invariant enforcement** — Status combinations follow the invariant table
6. **Archived files declaration** — `archived_files` map in metadata matches actual file presence

Verification runs twice during archival:
- After initial write (pre-finalization)
- After finalization metadata update (post-finalization)

**Source:** `governance/infrastructure/io_verify.py:69-402` — `verify_run_archive()`

## Identity Model

- **Repository identity:** 24-hex SHA-256 fingerprint derived from git remote URL or local path
- **Run identity:** Unique run ID per materialization cycle
- **Deterministic hashing:** `governance/domain/canonical_json.py` — `canonical_json_hash()` for reproducible content digests

## Related Documentation

- [Record Finalization & Verify Guide](record-finalization-verify-guide.md)
- [Data Retention & Deletion Policy](data-retention-deletion-policy.md)
- [Regulated Mode Operational Guide](regulated-mode-operational-guide.md)
- [Roles & Responsibilities Matrix](roles-and-responsibilities-matrix.md)
- [Customer Control Mapping](customer-control-mapping.md)

## Source References

| Component | File | Lines |
|---|---|---|
| Run artifact builder | `governance/infrastructure/run_audit_artifacts.py` | 190 |
| Archive orchestrator | `governance/infrastructure/work_run_archive.py` | 254 |
| Verify layer | `governance/infrastructure/io_verify.py` | 456 |
| Workspace paths | `governance/infrastructure/workspace_paths.py` | 235 |
| Atomic writes | `governance/infrastructure/fs_atomic.py` | 92 |
| Audit contract model | `governance/domain/audit_contract.py` | 547 |
| Canonical JSON hash | `governance/domain/canonical_json.py` | 46 |
