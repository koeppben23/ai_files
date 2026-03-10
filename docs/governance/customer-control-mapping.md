# Customer Control Mapping

**Version:** 1.1.0-RC.2
**Last Updated:** 2026-03-10

## Purpose

This document maps the governance system's implemented controls to typical regulatory control questions. It enables a regulated customer to understand how the system addresses specific compliance requirements without reading implementation code.

## Control Mapping Table

### 1. Traceability

**Regulatory Question:** Can we trace who did what, when, and why?

| Control | Implementation | Source |
|---|---|---|
| Provenance records | Every run archives a provenance record documenting trigger, binding, launcher, policy fingerprint, and timestamps | `governance/infrastructure/run_audit_artifacts.py:133-154` |
| Run manifests | Every run has a manifest documenting lifecycle status, run type, and artifact completeness | `governance/infrastructure/run_audit_artifacts.py:37-71` |
| Deterministic timestamps | All timestamps are RFC3339 UTC Z format, cross-checked across documents | `governance/infrastructure/io_verify.py:155-290` |

**Schema:** `governance.provenance-record.v1`

### 2. Immutability

**Regulatory Question:** Can finalized records be tampered with or altered?

| Control | Implementation | Source |
|---|---|---|
| SHA-256 checksums | Every archive file has a SHA-256 checksum in `checksums.json` | `governance/infrastructure/run_audit_artifacts.py:169-177` |
| Checksum recomputation | Verification re-reads files and recomputes hashes | `governance/infrastructure/io_verify.py:69-402` |
| Double verification | Verification runs before and after finalization | `governance/infrastructure/work_run_archive.py:172-194` |
| Duplicate prevention | Non-failed archive slots cannot be overwritten | `governance/infrastructure/work_run_archive.py:64-77` |
| Fail-closed verification | Any checksum mismatch causes immediate failure | `governance/domain/audit_contract.py:50-52` |

**Schema:** `governance.run-checksums.v1`

### 3. Completeness

**Regulatory Question:** Are all required records present and accounted for?

| Control | Implementation | Source |
|---|---|---|
| Required file enforcement | 5 mandatory files verified on every archive | `governance/domain/audit_contract.py:55-61` |
| Run-type artifact rules | Plan runs require plan-record, PR runs require pr-record | `governance/domain/audit_contract.py:173-177` |
| Archived files declaration | Metadata declares which files are present; verified against reality | `governance/infrastructure/io_verify.py:318-369` |
| Cross-document consistency | Run ID, fingerprint, timestamps verified across all documents | `governance/domain/audit_contract.py:340-398` |

**Schema:** `governance.audit-contract.v1`

### 4. Access Separation

**Regulatory Question:** Who can access, modify, or delete records?

| Control | Implementation | Source |
|---|---|---|
| Role-based access control | 5 roles with explicit permission matrix | `governance/domain/access_control.py` |
| Default deny | Unrecognized actions are denied (fail-closed) | `governance/assets/config/access_control_policy.yaml:72-76` |
| Regulated mode blocks | Operator purge blocked in regulated mode | `governance/domain/access_control.py` — `REGULATED_MODE_BLOCKED` |
| Compliance officer exclusives | Retention and redaction changes require CO role | `governance/domain/access_control.py` — `REGULATED_MODE_REQUIRED` |
| Runtime/audit separation | Purge operates on allowlisted runtime files only | `governance/infrastructure/run_audit_artifacts.py:10-18, 180-189` |

**Schema:** `governance.access-control.v1`

### 5. Data Classification & Privacy

**Regulatory Question:** How is sensitive data handled in audit records?

| Control | Implementation | Source |
|---|---|---|
| Field-level classification | Every audit field classified as public/internal/confidential/restricted | `governance/domain/classification.py` — `FIELD_CLASSIFICATIONS` |
| Default classification | Unclassified fields default to INTERNAL with hash redaction | `governance/domain/classification.py:171-177` |
| Redaction strategies | Hash, mask, remove, truncate — applied per field on export | `governance/infrastructure/redaction.py` |
| Export profiles | Public audit, internal audit, full audit — control what is visible | `governance/assets/config/classification_policy.yaml:58-67` |

**Schema:** `governance.classification.v1`

### 6. Retention & Deletion

**Regulatory Question:** How long are records kept and can they be accidentally deleted?

| Control | Implementation | Source |
|---|---|---|
| Classification-based retention | 1-10 year retention per classification level | `governance/domain/retention.py` — `RETENTION_PERIODS` |
| Framework overrides | DATEV=10yr, GoBD=10yr, SOX=7yr, BaFin=5yr | `governance/domain/retention.py` — `FRAMEWORK_RETENTION_OVERRIDES` |
| Legal holds | Suspend deletion for specific runs/repos/all | `governance/domain/retention.py` — `LegalHold` |
| Deletion guards | Three-guard evaluation: hold → regulated → retention | `governance/domain/retention.py` — `evaluate_deletion()` |
| Fail-closed default | Unknown classification → 10-year retention | `governance/domain/retention.py:173` |

**Schema:** `governance.retention-policy.v1`

### 7. Exportability

**Regulatory Question:** Can records be exported for external review or legal proceedings?

| Control | Implementation | Source |
|---|---|---|
| Portable bundles | Export produces self-contained directory with all artifacts | `governance/infrastructure/archive_export.py` — `export_finalized_bundle()` |
| Export manifest | Every export includes machine-readable manifest | `governance/infrastructure/archive_export.py` — `EXPORT_MANIFEST_SCHEMA` |
| Redacted export | Optional field-level redaction on export | `governance/infrastructure/archive_export.py` (uses `redaction.py`) |
| Finalization required | Only finalized archives can be exported | `governance/infrastructure/archive_export.py` — `validate_archive_for_export()` |

### 8. Recoverability

**Regulatory Question:** Can records be restored if the primary system fails?

| Control | Implementation | Source |
|---|---|---|
| Bundle restore | Exported bundles can be restored and validated | `governance/infrastructure/archive_export.py` — `restore_from_bundle()` |
| Restore validation | Restored bundles are checked for completeness | `governance/infrastructure/archive_export.py` — `validate_restored_bundle()` |
| Integrity re-verification | Restored archives can be verified with `verify_run_archive()` | `governance/infrastructure/io_verify.py:69-402` |
| Atomic writes | All file operations use atomic write with retry | `governance/infrastructure/fs_atomic.py` |

### 9. Failure Transparency

**Regulatory Question:** What happens when the system fails, and is the failure documented?

| Control | Implementation | Source |
|---|---|---|
| Failure records | Failed archives write explicit failure metadata and manifest | `governance/infrastructure/work_run_archive.py:195-244` |
| Failure classification | 8 failure categories with severity and recovery strategies | `governance/domain/failure_model.py` |
| No silent failures | Failure is always recorded and the exception re-raised | `governance/infrastructure/work_run_archive.py:245` |
| Failed state lifecycle | `run_status=failed`, `record_status=invalidated` — cannot be confused with success | `governance/domain/audit_contract.py:143-151` |

**Schema:** `governance.failure-report.v1`

## Summary Matrix

| # | Control Area | Implemented | Formalized | Schema | Tests |
|---|---|---|---|---|---|
| 1 | Traceability | Yes (T4) | Yes (WI-1) | provenance-record.v1 | test_provenance_record_contract.py |
| 2 | Immutability | Yes (T5) | Yes (WI-1) | run-checksums.v1 | test_audit_verify.py |
| 3 | Completeness | Yes (T1-T3) | Yes (WI-1) | audit-contract.v1 | test_audit_contract_consistency.py |
| 4 | Access Separation | Yes (T7, WI-5) | Yes (WI-5) | access-control.v1 | test_workspace_audit_separation.py |
| 5 | Data Classification | Yes (WI-4) | Yes (WI-4) | classification.v1 | test_audit_security.py |
| 6 | Retention | Yes (WI-6) | Yes (WI-6) | retention-policy.v1 | — |
| 7 | Exportability | Yes (WI-6) | Yes (WI-6) | archive-export-manifest.v1 | test_audit_bundle.py |
| 8 | Recoverability | Yes (WI-6) | Yes (WI-6) | — | — |
| 9 | Failure Transparency | Yes (T6, WI-2) | Yes (WI-2) | failure-report.v1 | test_failure_semantics.py |

## Related Documentation

- [Audit Architecture Overview](audit-architecture-overview.md)
- [Data Retention & Deletion Policy](data-retention-deletion-policy.md)
- [Record Finalization & Verify Guide](record-finalization-verify-guide.md)
- [Regulated Mode Operational Guide](regulated-mode-operational-guide.md)
- [Roles & Responsibilities Matrix](roles-and-responsibilities-matrix.md)
