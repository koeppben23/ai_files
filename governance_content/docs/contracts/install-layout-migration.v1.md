---
contract: install-layout-migration
version: v1
status: archived
scope: Migration rules from install-layout v_current to v_next
owner: install.py
effective_version: archived
supersedes: null
conformance_suite: archived
---

# Install Layout Migration Contract — v1

> **Status:** archived | **Scope:** Historical migration draft for transitioning from v_current to v_next.
> Each migration defines trigger, forward steps, backward compatibility, rollback, and fail-closed reason code.

## Archived Notice

- This migration contract is archived and non-operative.
- It remains for audit traceability only.
- Runtime/live contract enforcement must reference active contracts only.

## 1. Migration Index

| ID | Name | Trigger | Reason Code on Drift |
|----|------|---------|---------------------|
| M1 | State directory separation | Version bump to v_next | `BLOCKED-CONTRACT-LAYOUT-DRIFT` |
| M2 | Pointer file rename | Version bump to v_next | `BLOCKED-CONTRACT-LAYOUT-DRIFT` |
| M3 | Artifact classification enforcement | Version bump to v_next | `BLOCKED-CONTRACT-LAYOUT-DRIFT` |

## 2. M1 — State Directory Separation

### Trigger
Installer detects `effective_version >= v_next` in deployment configuration.

### Forward Migration Steps

1. Create `state/canonical/`, `state/derived/`, `state/transient/` under each `<fingerprint>/` workspace.
2. Move canonical artifacts (`SESSION_STATE.json`, `plan-record.json`, `plan-record-archive/`, `evidence/`, `repo-identity-map.yaml`) into `state/canonical/`.
3. Move derived artifacts (`repo-cache.yaml`, `repo-map-digest.md`, `workspace-memory.yaml`, `decision-pack.md`, `business-rules.md`, `business-rules-status.md`) into `state/derived/`.
4. Move transient artifacts (`locks/`, `logs/`, `__pycache__/`) into `state/transient/`.
5. Update `workspace_paths.py` path functions to resolve through `state/<class>/` prefix.
6. Write migration marker: `<fingerprint>/state/.migration-marker.json` with schema, timestamp, source version, target version.

### Backward Compatibility
- All path resolution functions must check legacy flat location as fallback for one release cycle.
- Read path: `state/<class>/<artifact>` first, then `<artifact>` (flat fallback).
- Write path: always `state/<class>/<artifact>`.

### Rollback
1. Move all artifacts from `state/<class>/` back to `<fingerprint>/` root.
2. Remove `state/` directory tree.
3. Remove migration marker.
4. Revert `workspace_paths.py` to flat path resolution.

### Fail-Closed Behavior
If migration fails at any step:
- Emit `BLOCKED-CONTRACT-LAYOUT-DRIFT` with `failure_class: "migration-incomplete"`.
- Do NOT partially migrate — either all workspaces complete or none.
- Leave workspace in last consistent state (pre-migration flat layout).

## 3. M2 — Pointer File Rename

### Trigger
Installer detects `effective_version >= v_next` in deployment configuration.

### Forward Migration Steps

1. Read existing `${CONFIG_ROOT}/SESSION_STATE.json` pointer payload.
2. Validate payload against `opencode-session-pointer.v1` schema.
3. Write payload to `${CONFIG_ROOT}/active-workspace-pointer.json` using `atomic_write_text`.
4. Verify new file is readable and valid.
5. Remove legacy `${CONFIG_ROOT}/SESSION_STATE.json`.
6. Update `workspace_paths.py:global_pointer_path()` to return new filename.

### Backward Compatibility
- `read_pointer_file()` in `workspace_ready_gate.py` must check `active-workspace-pointer.json` first, then fall back to `SESSION_STATE.json`.
- `session_pointer.py:LEGACY_POINTER_SCHEMAS` extended to include filename-based legacy detection.
- One release cycle of dual-read support.

### Rollback
1. Copy `active-workspace-pointer.json` back to `SESSION_STATE.json`.
2. Remove `active-workspace-pointer.json`.
3. Revert path function.

### Fail-Closed Behavior
If rename fails:
- Emit `BLOCKED-CONTRACT-LAYOUT-DRIFT` with `failure_class: "pointer-rename-failed"`.
- Keep legacy `SESSION_STATE.json` intact — do NOT delete until new file is verified.

## 4. M3 — Artifact Classification Enforcement

### Trigger
All workspaces have completed M1 (state directory separation).

### Forward Migration Steps

1. Add `WORKSPACE_ARTIFACT_CLASSIFICATION` dict to `workspace_paths.py`.
2. Update `purge_runtime_state()` to use classification for purge decisions.
3. Update backup logic to use classification for backup scope.
4. Add conformance test validating every artifact in `workspace_paths.py` has a classification entry.

### Backward Compatibility
- Classification is additive metadata — does not change file locations (M1 handles that).
- Existing purge allowlist in `install.py:2644-2665` must be derived from classification, not hardcoded.

### Rollback
1. Remove `WORKSPACE_ARTIFACT_CLASSIFICATION` dict.
2. Restore hardcoded purge allowlist.

### Fail-Closed Behavior
If an artifact exists in `workspace_paths.py` without a classification entry:
- Emit `BLOCKED-CONTRACT-LAYOUT-DRIFT` with `failure_class: "unclassified-artifact"`.
- Block purge operations until classification is complete.

## 5. Migration Ordering Constraints

```text
M1 (state directory separation)
  └── M2 (pointer file rename)  [independent, can run in parallel]
  └── M3 (artifact classification)  [depends on M1 completion]
```

- M1 and M2 are independent and may execute in either order.
- M3 requires M1 to be complete (classification assumes `state/<class>/` structure).
- All three must complete before v_next is declared active.

## 6. Verification Checklist

After all migrations complete:

- [ ] Every workspace has `state/canonical/`, `state/derived/`, `state/transient/`
- [ ] No workspace artifacts remain at flat `<fingerprint>/` root (except `current_run.json`, `marker.json`, `runs/`)
- [ ] Global pointer uses `active-workspace-pointer.json` filename
- [ ] Legacy `SESSION_STATE.json` at config root is removed
- [ ] `WORKSPACE_ARTIFACT_CLASSIFICATION` covers every artifact in `workspace_paths.py`
- [ ] `purge_runtime_state()` uses classification-driven purge logic
- [ ] All conformance tests pass on all three OS platforms
- [ ] No `BLOCKED-CONTRACT-LAYOUT-DRIFT` reason codes are active
