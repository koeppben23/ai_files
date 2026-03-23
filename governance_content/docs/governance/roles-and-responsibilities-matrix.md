# Roles & Responsibilities Matrix

**Version:** 1.1.0-RC.2
**Contract:** ACCESS_CONTROL.v1
**Last Updated:** 2026-03-10

## Purpose

This document defines the role-based access control model for the governance audit system, including role definitions, the permission matrix, and four-eyes rules for regulated customers.

## Roles

| Role | Description | Default Classification Access |
|---|---|---|
| `operator` | System operator with full access in non-regulated mode | `internal` |
| `auditor` | External or internal auditor with read and verify access | `internal` |
| `compliance_officer` | Compliance officer with full access including retention management | `restricted` |
| `system` | Automated system operations | `internal` |
| `readonly` | Read-only user with limited metadata access | `public` |

**Source:** `governance_runtime/domain/access_control.py` — `Role` enum, `governance_runtime/assets/config/access_control_policy.yaml:20-35`

## Permission Matrix

### Standard Mode (Regulated Mode Inactive)

| Action | operator | auditor | compliance_officer | system | readonly |
|---|---|---|---|---|---|
| `read_archive` | ALLOW | ALLOW | ALLOW | ALLOW | DENY |
| `export_archive` | ALLOW | DENY | ALLOW | DENY | DENY |
| `verify_archive` | ALLOW | ALLOW | ALLOW | ALLOW | DENY |
| `purge_archive` | ALLOW | DENY | ALLOW | DENY | DENY |
| `read_failure_report` | ALLOW | ALLOW | ALLOW | ALLOW | DENY |
| `export_redacted` | ALLOW | ALLOW | ALLOW | ALLOW | DENY |
| `modify_retention` | ALLOW | DENY | ALLOW | DENY | DENY |
| `view_classification` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| `override_redaction` | DENY | DENY | ALLOW | DENY | DENY |

**Source:** `governance_runtime/domain/access_control.py` — `PERMISSION_TABLE`

### Regulated Mode Modifications

When regulated mode is active, the following overrides apply:

| Role | Action | Standard | Regulated | Reason |
|---|---|---|---|---|
| `operator` | `purge_archive` | ALLOW | **DENY** | Purge blocked for operators |
| `compliance_officer` | `modify_retention` | ALLOW | ALLOW (exclusive) | Only CO can modify retention |
| `compliance_officer` | `override_redaction` | ALLOW | ALLOW (audit-logged) | Only CO can override redaction |

**Source:** `governance_runtime/domain/access_control.py` — `REGULATED_MODE_BLOCKED`, `REGULATED_MODE_REQUIRED`

## Default Deny Policy

The access control model is **fail-closed**: any action not explicitly permitted is denied.

```
Default decision: DENY
Reason: "No explicit permission — fail-closed"
Audit log required: true
```

**Source:** `governance_runtime/assets/config/access_control_policy.yaml:72-76`

## Access Evaluation

Access is evaluated by `evaluate_access()`:

```
evaluate_access(role, action, regulated_mode_active) → AccessDecision
```

1. Check regulated mode blocked actions
2. Check regulated mode required actions
3. Check permission table
4. If no explicit permission found → DENY (fail-closed)

**Source:** `governance_runtime/domain/access_control.py` — `evaluate_access()`

## Four-Eyes Principle

For sensitive operations in regulated mode, the system supports separation of duties:

- **Retention modification** requires `compliance_officer` role (cannot be performed by `operator`)
- **Redaction override** requires `compliance_officer` role with audit logging
- **Archive purge** is blocked for `operator` in regulated mode

These constraints ensure that no single role can both create and destroy audit evidence.

## Audit Logging

All access decisions are audit-logged when regulated mode is active (`access_audit_logged` constraint). The audit log captures:
- Role
- Action attempted
- Decision (allow/deny)
- Timestamp
- Reason

## Related Documentation

- [Regulated Mode Operational Guide](regulated-mode-operational-guide.md)
- [Customer Control Mapping](customer-control-mapping.md)
- [Audit Architecture Overview](audit-architecture-overview.md)
