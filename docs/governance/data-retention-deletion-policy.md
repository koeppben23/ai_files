# Data Retention & Deletion Policy

**Version:** 1.1.0-RC.2
**Contract:** RETENTION_POLICY.v1
**Last Updated:** 2026-03-10

## Purpose

This document defines how long audit records are retained, when they may be deleted, and what safeguards prevent premature or unauthorized deletion. It is intended for regulated customer compliance reviews.

## Retention Periods

Retention periods are determined by the data classification level of the highest-sensitivity field in the archive:

| Classification Level | Retention Class | Minimum Period | Use Case |
|---|---|---|---|
| `public` | Short | 365 days (1 year) | Non-sensitive operational data |
| `internal` | Standard | 1,095 days (3 years) | Internal operational records |
| `confidential` | Extended | 2,555 days (7 years) | Records with customer references, digests |
| `restricted` | Permanent | 3,650 days (10 years) | DATEV/GoBD-level records |

**Source:** `governance/domain/retention.py` — `RETENTION_PERIODS`

**Fail-closed default:** Unclassified data defaults to `restricted` / 10-year retention.

## Compliance Framework Overrides

When a compliance framework is active, its minimum retention overrides the classification-level period if longer:

| Framework | Minimum Days | Description |
|---|---|---|
| DATEV | 3,650 | German tax record retention (10 years) |
| GoBD | 3,650 | German commercial/tax law (10 years) |
| BaFin | 1,825 | German banking regulation (5 years) |
| SOX | 2,555 | US Sarbanes-Oxley (7 years) |
| GDPR | 365 | EU data protection (1 year minimum) |
| Basel III | 1,825 | International banking (5 years) |
| ISO 27001 | 1,095 | Information security (3 years) |

**Source:** `governance/domain/retention.py` — `FRAMEWORK_RETENTION_OVERRIDES`

The effective retention period is: `max(classification_level_minimum, framework_override)`.

## Deletion Evaluation

Before any archive record can be deleted, the system evaluates three guards in order:

1. **Legal Hold** — Active legal holds unconditionally block deletion
2. **Regulated Mode** — When regulated mode is active, the regulated-mode minimum (default: 3,650 days) must be satisfied
3. **Retention Period** — The effective retention period must have expired

Deletion is only allowed when all three guards pass.

**Source:** `governance/domain/retention.py` — `evaluate_deletion()`

### Deletion Decisions

| Decision | Meaning |
|---|---|
| `allowed` | All guards passed; deletion permitted |
| `blocked_retention` | Within retention period |
| `blocked_legal_hold` | Active legal hold applies |
| `blocked_regulated_mode` | Regulated mode minimum not met |

## Legal Holds

Legal holds suspend deletion for a specified scope until explicitly released.

### Scope Types

| Scope | Target | Effect |
|---|---|---|
| `run` | Specific run ID | Blocks deletion of one run archive |
| `repo` | Repository fingerprint | Blocks deletion of all runs for a repository |
| `all` | All records | Blocks all deletions system-wide |

### Legal Hold Lifecycle

```
NONE → ACTIVE → RELEASED
```

- **Creating** a hold requires: `hold_id`, `scope_type`, `scope_value`, `reason`, `created_at`, `created_by`
- **Releasing** a hold additionally requires: `released_at`, `released_by`
- Only `ACTIVE` holds block deletion; `RELEASED` and `NONE` holds are inert

**Source:** `governance/domain/retention.py` — `LegalHold`, `validate_legal_hold()`

Legal hold records are persisted as JSON files in the holds directory:
`governance/infrastructure/archive_export.py` — `write_legal_hold_record()`, `load_legal_holds()`

## Workspace vs. Audit Store Separation

| Concern | Location | Cleanup |
|---|---|---|
| Runtime artifacts | `${WORKSPACES_HOME}/<fp>/` | `purge_runtime_artifacts()` — allowlisted files only |
| Audit archives | `${WORKSPACES_HOME}/governance-records/<fp>/runs/` | Retention policy + deletion guards |

Runtime cleanup (`purge_runtime_artifacts`) never touches the audit store. The allowlist is defined in `run_audit_artifacts.py:10-18` — `RUNTIME_PURGE_SAFE_FILES`.

## Export

Finalized archives can be exported as self-contained bundles:

- Export validates the archive (finalized status, all required files present)
- Optional field-level redaction based on classification policy
- Produces an `export-manifest.json` documenting the export
- Export refuses to overwrite existing bundles (no accidental overwrites)

**Source:** `governance/infrastructure/archive_export.py` — `export_finalized_bundle()`

## Restore

Exported bundles can be restored and validated:

- Bundle validation checks file completeness and manifest presence
- After restore, the caller should run `verify_run_archive()` for full integrity verification

**Source:** `governance/infrastructure/archive_export.py` — `restore_from_bundle()`, `validate_restored_bundle()`

## Policy Configuration

The retention policy is defined in `governance/assets/config/retention_policy.yaml` (POLICY-BOUND, pack-locked). The JSON schema is `governance/assets/schemas/retention_policy.v1.schema.json`.

## Related Documentation

- [Audit Architecture Overview](audit-architecture-overview.md)
- [Regulated Mode Operational Guide](regulated-mode-operational-guide.md)
- [Customer Control Mapping](customer-control-mapping.md)
