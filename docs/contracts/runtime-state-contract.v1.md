---
contract: runtime-state
version: v1
status: active
scope: Runtime state classification, pointer semantics, backup/purge/recovery rules
owner: governance/infrastructure/workspace_paths.py + governance/infrastructure/session_pointer.py
effective_version: 0.1.0
supersedes: null
conformance_suite: tests/conformance/test_runtime_state_conformance.py
---

# Runtime State Contract — v1

> **Status:** active | **Scope:** Formal state classification taxonomy, pointer semantics policy,
> and per-class backup/purge/recovery rules for all workspace artifacts.

## 1. State Classification Taxonomy

This contract introduces THREE formal state classes for workspace artifacts.
**This taxonomy is NEW** — no formal classification exists in the codebase today.
All artifacts in `workspace_paths.py` are assigned exactly one class.

### 1.1 Classification Table

| Artifact | File/Dir | Class | Rationale |
|----------|----------|-------|-----------|
| `SESSION_STATE.json` (workspace) | file | **canonical** | Authoritative session state; source of truth for active session |
| `plan-record.json` | file | **canonical** | Active plan record; drives phase-4 gate |
| `plan-record-archive/` | dir | **canonical** | Finalized plan records; audit trail |
| `evidence/` | dir | **canonical** | Workspace evidence; audit and compliance trail |
| `repo-identity-map.yaml` | file | **canonical** | Repo identity mapping; fingerprint-to-metadata binding |
| `current_run.json` | file | **canonical** | Current run pointer; drives run lifecycle |
| `marker.json` | file | **canonical** | Workspace ready marker; proves initialization completed |
| `repo-cache.yaml` | file | **derived** | Derived from repo analysis; regenerable |
| `repo-map-digest.md` | file | **derived** | Derived from repo analysis; regenerable |
| `workspace-memory.yaml` | file | **derived** | Derived from session history; regenerable |
| `decision-pack.md` | file | **derived** | Derived from business rules analysis; regenerable |
| `business-rules.md` | file | **derived** | Derived from repo analysis; regenerable |
| `business-rules-status.md` | file | **derived** | Derived from repo analysis; regenerable |
| `locks/` | dir | **transient** | Lock directory; lifecycle-bound to process |
| `runs/` | dir | **canonical** | Archived session runs; audit trail |

### 1.2 Class Definitions

| Class | Definition | Survives Upgrade | Backup Required | Safe to Purge |
|-------|-----------|-----------------|----------------|--------------|
| **canonical** | Source of truth; authoritative data that cannot be regenerated from other artifacts | Yes | Yes (before migration/upgrade) | Only with explicit operator consent |
| **derived** | Regenerable from canonical data + external sources (repo analysis, session history) | Best-effort | Optional | Yes — will be regenerated on next session |
| **transient** | Operational artifacts with no cross-session value; process-lifetime or shorter | No | Never | Always safe |

## 2. Pointer Semantics Policy

### 2.1 Global Pointer

| Attribute | Value |
|-----------|-------|
| **Location** | `${CONFIG_ROOT}/SESSION_STATE.json` |
| **Schema** | `opencode-session-pointer.v1` |
| **Purpose** | Activation and routing ONLY |
| **Keys** | `activeRepoFingerprint`, `activeSessionStateFile`, `activeSessionStateRelativePath` |
| **Written by** | `workspace_ready_gate.py:ensure_workspace_ready` via `atomic_write_text` |
| **Semantics** | Points to the currently active workspace — does NOT contain session state |

**Naming note:** The file is confusingly named `SESSION_STATE.json` at the config-root level, but it is purely a routing pointer. The canonical session state lives at the workspace level. A future rename is documented in `install-layout-contract.v_next.md` — but the current contract uses the existing name.

### 2.2 Workspace State

| Attribute | Value |
|-----------|-------|
| **Location** | `${WORKSPACES_HOME}/<fingerprint>/SESSION_STATE.json` |
| **Schema** | Session state schema (per `SESSION_STATE_SCHEMA.md`) |
| **Purpose** | Canonical truth for the active session |
| **Written by** | Governance kernel (session lifecycle) |
| **Semantics** | Contains actual session state: phase, gates, evidence references, reason codes |

### 2.3 Policy Rules

1. **Global pointer = activation/routing.** Never read the global pointer as if it were session state.
2. **Workspace state = canonical truth.** All session state reads must target the workspace `SESSION_STATE.json`.
3. **Pointer and state must not be confused.** Code that reads the global pointer must route through `governance/infrastructure/session_pointer.py` (`parse_session_pointer_document(...)` + `resolve_active_session_state_path(...)` for read paths, `parse_pointer_payload(...)` for strict write/validation paths). Code that reads session state must use the session state schema.
4. **Session state is NEVER at repo root.** `bootstrap_persistence.py` explicitly blocks `config_root` inside `repo_root`.
5. **Future rename only with migration.** The global pointer may only be renamed through a formal migration (see `install-layout-migration.v1.md`, M2). No ad-hoc renaming.
6. **Business-rules hydration is workspace-state only.** Pointer-shaped documents are rejected before business-rules hydration or persistence can treat them as `SESSION_STATE`.

### 2.4 Run Pointer

| Attribute | Value |
|-----------|-------|
| **Location** | `${WORKSPACES_HOME}/<fingerprint>/current_run.json` |
| **Schema** | `governance.current-run-pointer.v1` |
| **Purpose** | Points to the currently active run within a workspace |
| **Archived runs** | `${WORKSPACES_HOME}/<fingerprint>/runs/<run_id>/` |

### 2.5 Legacy Pointer Schema Migration

`workspace_ready_gate.py:read_pointer_file` transparently migrates legacy pointer schemas:
- Supported legacy schemas: `active-session-pointer.v1` (in `LEGACY_POINTER_SCHEMAS`)
- Legacy key mapping: `repo_fingerprint` → `activeRepoFingerprint`, etc.
- Migration is transparent on read: read legacy → write canonical format back

## 3. Backup/Purge/Recovery Rules per Class

### 3.1 Purge Rules

**Source of truth:** `install.py:2572-2679` (`purge_runtime_state`)

| Class | Purge Behavior | Controlled By |
|-------|---------------|--------------|
| **canonical** | Purged by default on uninstall | `--keep-workspace-state` to preserve |
| **derived** | Purged by default on uninstall | `--keep-workspace-state` to preserve |
| **transient** | Purged by default on uninstall | `--keep-workspace-state` to preserve |

**Current reality:** All three classes are purged together by `purge_runtime_state`. The v_current purge implementation uses an allowlist of 9 flat files + 3 subtrees — it does NOT use the classification taxonomy. The taxonomy formalizes the _intent_ for future class-aware purge logic.

### 3.2 Purge Allowlist (Current Implementation)

**Flat files purged per workspace (9):**
`SESSION_STATE.json`, `repo-identity-map.yaml`, `repo-cache.yaml`, `repo-map-digest.md`,
`workspace-memory.yaml`, `decision-pack.md`, `business-rules.md`, `business-rules-status.md`,
`plan-record.json`

**Subtrees purged per workspace (3):**
`plan-record-archive/`, `evidence/`, `.lock/`

**Config-root level purge targets (2):**
`governance.activation_intent.json`, `SESSION_STATE.json` (global pointer)

**Never purged:**
`opencode.json` — enforced by three runtime assertions (see `opencode-integration-contract.v1.md`)

### 3.3 Backup Rules

| Class | Backup Recommendation | Backup Trigger |
|-------|----------------------|----------------|
| **canonical** | Required before migration or major version upgrade | Pre-migration, pre-upgrade |
| **derived** | Optional; can be regenerated | Not typically backed up |
| **transient** | Never backed up | — |

### 3.4 Recovery Rules

| Scenario | Recovery Strategy |
|----------|------------------|
| Canonical artifact corrupted | Restore from backup; if no backup, re-bootstrap workspace |
| Derived artifact corrupted | Delete and let next session regenerate |
| Transient artifact stale | Delete; will be recreated on next operation |
| Global pointer corrupted | Re-bootstrap; `workspace_ready_gate.py` will rewrite |
| Workspace lock stuck | Stale lock detection (TTL 120s) auto-reclaims; or manual `rmdir locks/workspace.lock/` |
| Session state schema mismatch | Emit `WARN-SESSION-STATE-SCHEMA-VIOLATION`; do not auto-migrate |

## 4. Artifact Completeness Invariant

Every artifact returned by any function in `workspace_paths.py` MUST appear in the classification table in section 1.1. If an artifact is added to `workspace_paths.py` without a corresponding classification entry, this constitutes a contract violation and should trigger `BLOCKED-CONTRACT-RUNTIME-DRIFT`.

## 5. Cross-Contract References

| Contract | Relationship |
|----------|-------------|
| `install-layout-contract.v_current` | Defines the physical layout this contract classifies |
| `install-layout-contract.v_next` | Defines the `state/` subdirectory that will physically separate classes |
| `install-layout-migration.v1` | Defines how to migrate from flat to classified layout |
| `opencode-integration-contract.v1` | Defines the never-delete guarantee for `opencode.json` |
