---
contract: opencode-integration
version: v1
status: active
scope: OpenCode Desktop bridge configuration, plugin lifecycle, rail injection invariants
owner: install.py + governance/artifacts/opencode-plugins/audit-new-session.mjs
effective_version: 0.1.0
supersedes: null
conformance_suite: tests/conformance/test_opencode_integration_conformance.py
---

# OpenCode Integration Contract — v1

> **Status:** active | **Scope:** opencode.json generation, merge-ownership, plugin lifecycle,
> Python resolution, rail injection, and uninstall guarantee.

## 1. opencode.json — Merge Ownership

**Source of truth:** `install.py:1281-1342` (`ensure_opencode_json`)

### 1.1 Location

`${CONFIG_ROOT}/opencode.json`

### 1.2 Ownership Model

opencode.json is classified as **user/team configuration**, not installer-owned runtime state. It may be checked into version control and shared across team members.

### 1.3 Merge Rules (Append-Only)

| Rule | Behavior | Source |
|------|----------|--------|
| **Fresh install** | Create with `instructions` array + `plugin` array | `install.py:1329-1342` |
| **Existing file** | Merge: add missing instruction entries, never remove existing | `install.py:1294-1327` |
| **User keys** | All non-`instructions`/non-`plugin` keys are preserved untouched | `install.py:1309` (only `instructions` and `plugin` are modified) |
| **Instruction order** | Existing instruction order preserved; new entries appended at end | `install.py:1305-1308` |
| **Plugin merge** | Plugin URI appended if not already present; existing entries preserved | `install.py:1311-1317` |
| **Corrupt file** | Treated as empty dict; governance entries added fresh | `install.py:1297-1300` |
| **Non-dict file** | Treated as empty dict; governance entries added fresh | `install.py:1297-1298` |
| **Instructions not list** | Treated as empty list; governance entries added fresh | `install.py:1303-1304` |

### 1.4 Governance Instructions (Canonical Set)

```python
OPENCODE_INSTRUCTIONS = [
    "commands/master.md",
    "commands/rules.md",
    "commands/SESSION_STATE_SCHEMA.md",
    "commands/README-OPENCODE.md",
]
```

### 1.5 Idempotency

Repeated calls to `ensure_opencode_json` must produce identical output. No duplicate entries in `instructions` or `plugin` arrays after any number of install/reinstall cycles.

## 2. Plugin Lifecycle

**Source of truth:** `install.py:1274-1276`, `install.py:1345-1369`, `governance/artifacts/opencode-plugins/audit-new-session.mjs`

### 2.1 Install Phase

1. Plugin source: `governance/artifacts/opencode-plugins/audit-new-session.mjs`
2. Installed to: `${CONFIG_ROOT}/opencode-plugins/audit-new-session.mjs`
3. Plugin URI: `file:///.../<config_root>/opencode-plugins/audit-new-session.mjs` (resolved via `Path.as_uri()`)
4. URI registered in `opencode.json` under the `"plugin"` key (array)

### 2.2 Runtime Phase

The plugin (`audit-new-session.mjs`) operates as follows:

| Aspect | Behavior |
|--------|----------|
| **Trigger** | `session.created` events only; ignores `file.watcher.updated` and all other event types |
| **Deduplication** | In-memory `seen` Set keyed by session ID; per-process lifetime |
| **Repo root resolution** | Priority cascade: `event.properties.info.directory` > `event.properties.directory` > `client.repo_root/repoRoot/cwd` > `process.cwd()` (fallback requires plausibility check) |
| **Plausibility check** | Directory must contain at least one of: `.git`, `governance`, `governance.paths.json`, `pyproject.toml`, `package.json` |
| **Governance invocation** | Spawns `python -m governance_runtime.entrypoints.new_work_session --trigger-source desktop-plugin --quiet` |
| **Output cap** | stdout/stderr capped at 64KB per stream |
| **Failure mode** | Non-blocking; errors logged via `client.app.log()` best-effort |

### 2.3 Uninstall Phase

1. Plugin URI is removed from `opencode.json` `"plugin"` array via `remove_installer_plugin_from_opencode_json`
2. Only the installer's own plugin URI is removed; other plugin entries preserved
3. The `opencode.json` file itself is **NEVER deleted**
4. The plugin file at `${CONFIG_ROOT}/opencode-plugins/audit-new-session.mjs` is deleted

## 3. Python Resolution Order

**Source of truth:** `audit-new-session.mjs:128-181` (`resolvePython`)

| Priority | Check | Platform |
|----------|-------|----------|
| 1 | `OPENCODE_PYTHON` environment variable | All |
| 2 | `py -3 -V` (Python Launcher) | Windows only |
| 3 | `python -V` | Windows only |
| 4 | `python3 -V` | Unix/macOS |
| 5 | `python -V` | Unix/macOS |

If no Python interpreter is found, the plugin logs a warning and skips governance invocation entirely. It does NOT fail-hard — the session proceeds without governance audit.

## 4. Rail Injection Invariants

**Source of truth:** `install.py:1372-1451` (`inject_session_reader_path_for_command`)

### 4.1 Placeholders

| Placeholder | Replaced With |
|-------------|--------------|
| `{{SESSION_READER_PATH}}` | Absolute path to `${COMMANDS_HOME}/governance/entrypoints/session_reader.py` |
| `{{PYTHON_COMMAND}}` | Detected Python command (auto-quoted if single-token path with spaces) |

### 4.2 Injection Targets

Rail injection is applied to installed command markdown templates:
- `continue.md`
- `review.md`
- `plan.md`
- `ticket.md`
- `review-decision.md`

### 4.3 Python Command Quoting

| Input | Contains Path Separators? | Result |
|-------|--------------------------|--------|
| `python3` | No | `python3` (unquoted) |
| `py -3` | No | `py -3` (unquoted, multi-token) |
| `C:\Program Files\Python311\python.exe` | Yes + has spaces | `"C:\Program Files\Python311\python.exe"` (quoted) |
| `/usr/bin/python3` | Yes, no spaces | `/usr/bin/python3` (unquoted) |

### 4.4 Legacy Fallback

If neither `{{SESSION_READER_PATH}}` nor `{{PYTHON_COMMAND}}` placeholders are found, a legacy regex pattern matches older `python "...session_reader.py"` invocations and replaces them. If no match is found, the file is left unchanged (`status: "skipped-no-placeholder"`).

## 5. Uninstall Guarantee

**Source of truth:** `install.py:2109-2114`

> opencode.json is NEVER deleted on uninstall. Neither `delete_targets()` nor `purge_runtime_state()` touch this file.

This guarantee is enforced by three runtime assertions:
1. `install.py:2109-2114` — policy comment block
2. `install.py:2606-2609` — `assert OPENCODE_JSON_NAME not in {...}` (config-root purge targets)
3. `install.py:2656-2658` — `assert OPENCODE_JSON_NAME not in workspace_artifact_names`

### Uninstall behavior for opencode.json:
- The **file** is preserved
- The installer's **plugin URI** is removed from the `"plugin"` array
- All **user keys** remain intact
- All **user-added instructions** remain intact
- Only governance-added instruction entries are orphaned (pointing to deleted command files)
