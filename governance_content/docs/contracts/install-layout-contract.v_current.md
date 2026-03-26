---
contract: install-layout
version: v_current
status: active
scope: Canonical install layout, workspace artifacts, ownership and retention rules
owner: governance_runtime/install/install.py + governance_runtime/infrastructure/workspace_paths.py
effective_version: 0.1.0
supersedes: null
conformance_suite: tests/conformance/test_layout_conformance.py
---

# Install Layout Contract — v_current

> **Status:** active | **Scope:** Current install layout reality as implemented.
> This document describes ONLY what exists today. No future elements.

## 1. Canonical Path Variables

| Variable | Resolution | Source |
|----------|-----------|--------|
| `${CONFIG_ROOT}` | OpenCode config root, runtime-resolved (e.g. `~/.config/opencode`) | `governance_runtime/paths/layout.py:ConfigLayout` |
| `${LOCAL_ROOT}` | OpenCode local payload root (e.g. `~/.local/share/opencode`) | installer (`OPENCODE_LOCAL_ROOT` override or default) |
| `${COMMANDS_HOME}` | `${CONFIG_ROOT}/commands` (default from installer binding evidence) | `governance_runtime/infrastructure/binding_paths.py` |
| `${PROFILES_HOME}` | `${LOCAL_ROOT}/governance_content/profiles` | `governance.paths.json` |
| `${PLUGINS_HOME}` | `${CONFIG_ROOT}/plugins` | installer (`install.py`) |
| `${WORKSPACES_HOME}` | `${CONFIG_ROOT}/workspaces` (default from installer binding evidence) | `governance_runtime/infrastructure/binding_paths.py` |
| `${SESSION_STATE_POINTER_FILE}` | `${CONFIG_ROOT}/SESSION_STATE.json` (global pointer) | `governance_runtime/infrastructure/workspace_paths.py:global_pointer_path` | |

### Supported Exception Sources

- **Trusted binding override:** `OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE=1` + `OPENCODE_TRUSTED_COMMANDS_HOME`
- **Dev cwd binding search:** `OPENCODE_ALLOW_CWD_BINDINGS=1`

Both must be explicit and auditable.

## 2. Installed Tree Shape

```text
${CONFIG_ROOT}/
  bin/
    opencode-governance-bootstrap      # Local launcher (POSIX)
    opencode-governance-bootstrap.cmd  # Local launcher (Windows)
  plugins/                        # = ${PLUGINS_HOME}
    audit-new-session.mjs         # OpenCode Desktop plugin
  opencode.json                   # OpenCode Desktop bridge config (user-owned)
  commands/                       # = ${COMMANDS_HOME}
    audit-readout.md
    continue.md
    implement.md
    implementation-decision.md
    plan.md
    review-decision.md
    review.md
    ticket.md
    INSTALL_MANIFEST.json         # Installer manifest (SHA256, paths)
  workspaces/                     # = ${WORKSPACES_HOME}
    <repo_fingerprint>/           # Per-repo workspace (see section 3)
  INSTALL_HEALTH.json             # Installer health status
  governance.paths.json          # Installer binding evidence

${LOCAL_ROOT}/
  governance_runtime/             # Canonical runtime authority
  governance_content/             # Canonical docs/profiles/templates content
  governance_spec/                # Canonical machine-readable specs/contracts
  governance/                     # Frozen compatibility surface only
  VERSION
```

## 3. Workspace Artifact Layout

All artifacts live under `${WORKSPACES_HOME}/<repo_fingerprint>/`.

The `repo_fingerprint` is a canonical 24-hex hash:
- Git remote: `SHA256("repo:" + canonical_remote)[:24]`
- Local path: `SHA256("repo:local:" + normalized_path)[:24]`

**Source of truth:** `governance_runtime/infrastructure/workspace_paths.py`

```text
${WORKSPACES_HOME}/<fingerprint>/
  SESSION_STATE.json              # Canonical session state (repo-scoped)
  repo-cache.yaml                 # Phase 2 artifact
  repo-map-digest.md              # Phase 2 artifact
  workspace-memory.yaml           # Phase 2 artifact
  decision-pack.md                # Phase 2.1 artifact
  business-rules.md               # Phase 1.5 artifact
  business-rules-status.md        # Phase 1.5 artifact
  plan-record.json                # Phase 4 artifact
  repo-identity-map.yaml          # Repo identity mapping
  current_run.json                # Current run pointer (schema: governance.current-run-pointer.v1)
  marker.json                     # Workspace ready marker (schema: workspace-ready-marker.v1)
  plan-record-archive/            # Finalized plan records rotated here
  evidence/                       # Workspace evidence directory
    repo-context.resolved.json    # Repo context evidence
  locks/                          # Workspace lock directory
    workspace.lock/               # Directory-as-mutex lock
      owner.json                  # Lock owner (PID + acquired_at)
  runs/                           # Archived session runs
    <run_id>/
      SESSION_STATE.json          # Run-specific session state snapshot
      plan-record.json            # Run-specific plan record snapshot
      metadata.json               # Run metadata
```

## 4. Per-Artifact Ownership and Mutability

| Artifact | Owner | Mutability | Created By |
|----------|-------|-----------|------------|
| `SESSION_STATE.json` (global) | kernel | write-on-activation | `workspace_ready_gate.py` |
| `governance.paths.json` | installer | write-on-install | `install.py` |
| `INSTALL_MANIFEST.json` | installer | write-on-install | `install.py` |
| `INSTALL_HEALTH.json` | installer | write-on-install | `install.py` |
| `opencode.json` | **user/team** | merge-on-install, **never deleted** | `install.py:ensure_opencode_json` |
| `governance.activation_intent.json` | kernel | write-on-bootstrap | bootstrap persistence |
| `SESSION_STATE.json` (workspace) | kernel | read-write per session | governance kernel |
| `repo-cache.yaml` | kernel | write per phase-2 | governance kernel |
| `repo-map-digest.md` | kernel | write per phase-2 | governance kernel |
| `workspace-memory.yaml` | kernel | write per phase-2 | governance kernel |
| `decision-pack.md` | kernel | write per phase-2.1 | governance kernel |
| `business-rules.md` | kernel | write per phase-1.5 | governance kernel |
| `business-rules-status.md` | kernel | write per phase-1.5 | governance kernel |
| `plan-record.json` | kernel | write per phase-4 | governance kernel |
| `repo-identity-map.yaml` | kernel | write-on-discovery | governance kernel |
| `current_run.json` | kernel | write-on-run-start | governance kernel |
| `marker.json` | kernel | write-on-workspace-ready | `workspace_ready_gate.py` |
| `evidence/` contents | kernel | append-only per session | governance kernel |
| `locks/` contents | kernel | transient (lock lifecycle) | `workspace_ready_gate.py` |
| `runs/` contents | kernel | append-only (archived runs) | governance kernel |
| `bin/*` launchers | installer | write-on-install | `install.py` |
| `opencode-plugins/*` | installer | write-on-install | `install.py` |
| `commands/*` tree (strict allowlist) | installer | write-on-install | `install.py` |
| `governance_content/profiles/*` tree | installer | write-on-install | `install.py` |

## 5. Uninstall and Retention Behavior

**Source of truth:** `install.py:2099-2348` (uninstall), `install.py:2572-2679` (purge_runtime_state)

### 5.1 Core Retention Rules

| Artifact | Uninstall Default | Flag to Override |
|----------|------------------|-----------------|
| `opencode.json` | **NEVER deleted** (asserted at `install.py:2109-2114`, `2606-2609`, `2656-2658`) | — |
| `governance.paths.json` | Preserved | `--purge-paths-file` to delete |
| Workspace state | **Purged** | `--keep-workspace-state` to preserve |
| Error logs | **Purged** | `--keep-error-logs` to preserve |
| `INSTALL_MANIFEST.json` | Deleted | — |
| `INSTALL_HEALTH.json` | Deleted | — |
| `bin/` launchers | Deleted | — |
| `commands/` tree | Deleted | — |
| `opencode-plugins/` | Deleted (plugin URI removed from opencode.json, file preserved) | — |

### 5.2 Purge Behavior (purge_runtime_state)

**Allowlist-only deletion.** Only these artifacts are removed per workspace:

**Flat files (9):**
`SESSION_STATE.json`, `repo-identity-map.yaml`, `repo-cache.yaml`, `repo-map-digest.md`,
`workspace-memory.yaml`, `decision-pack.md`, `business-rules.md`, `business-rules-status.md`,
`plan-record.json`

**Subtrees (3):**
`plan-record-archive/`, `evidence/`, `.lock/`

**Config-root level targets (2):**
`governance.activation_intent.json`, `SESSION_STATE.json` (global pointer)

Non-matching user files are explicitly preserved. Empty workspace directories are cleaned up after purge.

### 5.3 Uninstall Paths

1. **Manifest-based (preferred):** Uses `INSTALL_MANIFEST.json` entries + known installer-owned files
2. **Conservative fallback:** When manifest missing + `--force`; deletes only installer-owned files resolvable from source tree
3. **Blocked:** When manifest missing without `--force`; returns exit code 4

### 5.4 opencode.json Safety Invariants

Three runtime assertions enforce the never-delete guarantee:
- `install.py:2109-2114` — comment block establishing the policy
- `install.py:2606-2609` — `assert OPENCODE_JSON_NAME not in {...}` (config-root purge targets)
- `install.py:2656-2658` — `assert OPENCODE_JSON_NAME not in workspace_artifact_names`

## 6. Pointer Architecture (Current Reality)

- **Global pointer:** `${CONFIG_ROOT}/SESSION_STATE.json` — routes to active workspace
  - Schema: `opencode-session-pointer.v1`
  - Keys: `activeRepoFingerprint`, `activeSessionStateFile`, `activeSessionStateRelativePath`
  - Purpose: activation/routing ONLY (confusingly named — it is a pointer, not state)
- **Workspace state:** `${WORKSPACES_HOME}/<fingerprint>/SESSION_STATE.json` — canonical truth
- **Run pointer:** `${WORKSPACES_HOME}/<fingerprint>/current_run.json` — current run pointer
  - Schema: `governance.current-run-pointer.v1`
- Session state is NEVER at repo root; `bootstrap_persistence.py` explicitly blocks `config_root` inside `repo_root`

## 7. Config-Root Safety

`bootstrap_persistence.py` enforces:
- `config_root` must NOT resolve inside `repo_root` — error code `CONFIG_ROOT_INSIDE_REPO`
- `pointer_file` must NOT resolve inside `repo_root` — error code `POINTER_PATH_INSIDE_REPO`

This prevents workspace contamination and ensures governance state stays external to repositories.
