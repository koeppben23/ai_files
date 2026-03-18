---
contract: install-layout
version: v_next
status: archived
scope: Target install layout with state classification and dedicated pointer file
owner: install.py + governance/infrastructure/workspace_paths.py
effective_version: archived
supersedes: install-layout-contract.v_current
conformance_suite: archived
---

# Install Layout Contract — v_next (Planned Evolution)

> **Status:** archived | **Historical target architecture draft (not live contract).**
> **Nicht aktuell wirksam.** No element described here is implemented today.
> See `install-layout-contract.v_current.md` for current reality.

## 1. Motivation

The current layout has several structural ambiguities:

1. **Pointer/state naming confusion:** The global pointer file is named `SESSION_STATE.json`, which suggests it holds state — but it is purely a routing pointer.
2. **No formal artifact classification:** All workspace artifacts are flat peers; there is no distinction between canonical source-of-truth files, derived/cache files, and transient operational artifacts.
3. **No `state/` subdirectory:** All workspace artifacts live directly under `<fingerprint>/`, mixing long-lived canonical data with ephemeral caches and locks.

## 2. Target: state/ Subdirectory Separation

```text
${WORKSPACES_HOME}/<fingerprint>/
  state/                          # NEW — formal state subdirectory
    canonical/
      SESSION_STATE.json          # Canonical session state
      plan-record.json            # Active plan record
      plan-record-archive/        # Finalized plan records
      evidence/                   # Workspace evidence
      repo-identity-map.yaml      # Repo identity mapping
    derived/
      repo-cache.yaml             # Derived from repo analysis
      repo-map-digest.md          # Derived from repo analysis
      workspace-memory.yaml       # Derived from session history
      decision-pack.md            # Derived from business rules
      business-rules.md           # Derived from repo analysis
      business-rules-status.md    # Derived from repo analysis
    transient/
      locks/                      # Lock directory (lifecycle-bound)
      logs/                       # Session logs (ephemeral)
      __pycache__/                # Python cache (ephemeral)
  current_run.json                # Current run pointer (stays at root)
  marker.json                     # Workspace ready marker (stays at root)
  runs/                           # Archived runs (stays at root)
    <run_id>/
      SESSION_STATE.json
      plan-record.json
      metadata.json
```

### Classification Rules

| Class | Definition | Backup | Purge | Survives Upgrade |
|-------|-----------|--------|-------|-----------------|
| **canonical** | Source of truth; authoritative session/plan/evidence data | Required before migration | Only with explicit operator consent | Yes |
| **derived** | Regenerable from canonical data + repo analysis | Optional | Safe to purge; will be regenerated | Best-effort |
| **transient** | Operational artifacts with no cross-session value | Never | Always safe to purge | No |

## 3. Dedicated Pointer File

The global pointer file will be renamed from `SESSION_STATE.json` to a dedicated name that clearly communicates its routing-only purpose:

| Current | Target | Rationale |
|---------|--------|-----------|
| `${CONFIG_ROOT}/SESSION_STATE.json` | `${CONFIG_ROOT}/active-workspace-pointer.json` | Eliminates naming confusion with workspace `SESSION_STATE.json` |

### Migration Constraint

The rename may ONLY be performed with a formal migration (see `install-layout-migration.v1.md`). During the transition period:
- Both filenames must be checked on read (canonical first, legacy fallback)
- Only the new canonical name is written
- Legacy file is removed after successful read-through-new-path verification

## 4. Classified Workspace Structure

Every artifact in `workspace_paths.py` must carry a formal classification label. The v_next contract introduces a `WORKSPACE_ARTIFACT_CLASSIFICATION` registry:

```python
WORKSPACE_ARTIFACT_CLASSIFICATION: Final[dict[str, str]] = {
    "SESSION_STATE.json": "canonical",
    "plan-record.json": "canonical",
    "plan-record-archive/": "canonical",
    "evidence/": "canonical",
    "repo-identity-map.yaml": "canonical",
    "repo-cache.yaml": "derived",
    "repo-map-digest.md": "derived",
    "workspace-memory.yaml": "derived",
    "decision-pack.md": "derived",
    "business-rules.md": "derived",
    "business-rules-status.md": "derived",
    "locks/": "transient",
    "logs/": "transient",
    "__pycache__/": "transient",
}
```

This classification drives purge, backup, and migration behavior deterministically.

## 5. Impact on Existing Contracts

| Contract | Impact |
|----------|--------|
| `opencode-integration-contract.v1` | No change — opencode.json stays at `${CONFIG_ROOT}/` |
| `runtime-state-contract.v1` | Major — state classification taxonomy becomes enforced |
| Reason codes | New reason code `BLOCKED-CONTRACT-LAYOUT-DRIFT` gates on v_next violations |
| Conformance suites | New tests required for state/ subdirectory structure |

## 6. Non-Goals for v_next

- No change to `opencode.json` location or ownership
- No change to `governance.paths.json` schema
- No change to repo fingerprint algorithm
- No change to the `runs/` archive structure
- No change to the lock mechanism (directory-as-mutex stays)
