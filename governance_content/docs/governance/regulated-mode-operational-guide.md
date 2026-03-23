# Regulated Mode Operational Guide

**Version:** 1.1.0-RC.2
**Contract:** REGULATED_MODE.v1
**Last Updated:** 2026-03-10

## Purpose

This document explains what regulated mode enforces, when it applies, and what operational constraints it imposes. It is intended for compliance officers and system administrators operating the governance system for regulated customers.

## What Is Regulated Mode?

Regulated mode is an operating state that activates additional constraints on the governance system to meet the requirements of regulated industries (banking, tax, financial services). When active, the system enforces stricter controls on data retention, access, redaction, and archive immutability.

**Source:** `governance/domain/regulated_mode.py`

## Regulated Mode States

```
INACTIVE → ACTIVE
         ↘ TRANSITIONING (treated as ACTIVE — fail-closed)
```

| State | Effect |
|---|---|
| `INACTIVE` | Standard operation, no additional constraints |
| `ACTIVE` | All regulated constraints enforced |
| `TRANSITIONING` | Treated as ACTIVE (fail-closed) |

**Fail-closed:** If the mode state is ambiguous or transitioning, all regulated constraints are enforced.

**Source:** `governance/domain/regulated_mode.py:118-144` — `evaluate_mode()`

## Active Constraints

When regulated mode is active, the following constraints are enforced:

| Constraint | ID | Effect |
|---|---|---|
| Retention Locked | `retention_locked` | Retention periods cannot be shortened |
| Purge Authorization | `purge_requires_authorization` | Purge operations require elevated role |
| Access Audit Logging | `access_audit_logged` | All access events are audit-logged |
| Redaction Override Requires CO | `redaction_override_requires_compliance_officer` | Only compliance officer can override redaction |
| Tamper-Evident Export | `export_tamper_evident` | Exports include checksums and manifest |
| Archive Immutability | `archive_immutable` | Finalized archives cannot be modified |
| Classification Enforced | `classification_enforced` | Data classification is mandatory |

**Source:** `governance/domain/regulated_mode.py:83-91` — `ACTIVE_CONSTRAINTS`

## Retention in Regulated Mode

When regulated mode is active:

- Retention periods **cannot be shortened** below the framework minimum
- The minimum retention is determined by `max(config.minimum_retention_days, framework_minimum)`
- Default minimum: 3,650 days (10 years)
- Increasing retention is always allowed

### Retention Change Validation

```
validate_retention_change(config, current_days, requested_days) → (allowed, reason)
```

| Condition | Result |
|---|---|
| Regulated mode inactive | Always allowed |
| Below framework minimum | Blocked |
| Below current retention | Blocked (cannot shorten) |
| Above current and above minimum | Allowed |

**Source:** `governance/domain/regulated_mode.py:164-199` — `validate_retention_change()`

## Compliance Frameworks

The system recognizes these compliance frameworks with minimum retention requirements:

| Framework | Minimum Retention | Description |
|---|---|---|
| DATEV | 3,650 days (10 years) | German tax |
| GoBD | 3,650 days (10 years) | German commercial/tax law |
| BaFin | 1,825 days (5 years) | German banking |
| SOX | 2,555 days (7 years) | US Sarbanes-Oxley |
| GDPR | 365 days (1 year) | EU data protection |
| Basel III | 1,825 days (5 years) | International banking |
| ISO 27001 | 1,095 days (3 years) | Information security |
| DEFAULT | 365 days (1 year) | Fallback |

**Source:** `governance/domain/regulated_mode.py:102-111` — `COMPLIANCE_FRAMEWORKS`

## Access Control in Regulated Mode

Regulated mode modifies the access control matrix:

### Blocked Actions

| Role | Action | Reason |
|---|---|---|
| `operator` | `purge_archive` | Purge blocked for operators in regulated mode |

### Required Role Escalation

| Role | Action | Reason |
|---|---|---|
| `compliance_officer` | `modify_retention` | Only CO can change retention |
| `compliance_officer` | `override_redaction` | Only CO can override redaction (audit-logged) |

**Source:** `governance_runtime/assets/config/access_control_policy.yaml:59-70`

## Configuration

Regulated mode is configured via `RegulatedModeConfig`:

```
state: ACTIVE | INACTIVE | TRANSITIONING
customer_id: <customer identifier>
compliance_framework: DATEV | GoBD | BaFin | SOX | ...
minimum_retention_days: 3650
export_format: zip
require_checksums_on_export: true
```

**Source:** `governance/domain/regulated_mode.py:57-67` — `RegulatedModeConfig`

## Machine-Readable Summary

The `regulated_mode_summary()` function returns a machine-readable dict with:
- Contract version
- Current state and whether active
- Customer ID and compliance framework
- Minimum retention days
- List of active constraints
- Reason string

**Source:** `governance/domain/regulated_mode.py:202-214`

## Related Documentation

- [Roles & Responsibilities Matrix](roles-and-responsibilities-matrix.md)
- [Data Retention & Deletion Policy](data-retention-deletion-policy.md)
- [Customer Control Mapping](customer-control-mapping.md)
