---
contract: python-binding
version: v1
status: active
scope: Single Python Binding Authority — interpreter determination, persistence, and consumption across all runtime components
owner: install.py
effective_version: 0.1.0
supersedes: null
conformance_suite: tests/conformance/test_binding_conformance.py
---

# Python Binding Contract — v1

> **Status:** active | **Scope:** Deterministic interpreter binding for launcher, plugin,
> rails, and all governance entrypoints.

## 1. Core Policy

For every installation there is exactly one bound Python interpreter.
All runtime components must use exactly this interpreter.

### 1.1 Binding Rule

The installer determines the bound interpreter once, validates it, and persists
it as binding evidence. All runtime components consume exactly this binding.

### 1.2 Prohibition of Independent Resolution

> Runtime components **must not** independently probe `python`, `python3`, or
> `py -3` when a valid installation binding exists.
>
> PATH probing is only permitted as an explicitly documented degraded fallback
> when binding artifacts are missing or invalid.

### 1.3 Binding Determination

The installer resolves the interpreter via the following cascade (first match wins):

| Priority | Source | Resolution |
|----------|--------|------------|
| 1 | `OPENCODE_PYTHON` environment variable | Used as-is if the executable exists |
| 2 | `sys.executable` | The Python that executed the installer |

The resolved value is always an absolute, resolved filesystem path.

## 2. Binding Artifacts

Two artifacts persist the binding. Both are installer-owned and installer-written.

### 2.1 Semantic SSOT — `governance.paths.json`

**Location:** `${COMMANDS_HOME}/governance.paths.json`

The `paths.pythonCommand` field holds the bound interpreter as a POSIX-normalized
absolute path string. This is the authoritative semantic record of the binding.

All other binding representations are derived from this value.

### 2.2 Launcher Consumption Artifact — `PYTHON_BINDING`

**Location:** `${CONFIG_ROOT}/bin/PYTHON_BINDING`
**Format:** Single plain-text file. One line. Absolute interpreter path. No
trailing newline or whitespace beyond the path itself.

**Example content:**
```
/usr/bin/python3
```

**Windows example:**
```
C:/Users/dev/AppData/Local/Programs/Python/Python313/python.exe
```

**Properties:**
- Install-time artifact (not a repository file)
- Deterministically derived from `governance.paths.json:paths.pythonCommand`
- Written by the installer as the sole writer
- Consumable by shell scripts without JSON parsing
- Path format: POSIX-normalized absolute string (forward slashes, even on Windows)

### 2.3 Baked Launcher Path

Each launcher script (`.sh` / `.cmd`) contains a hardcoded `PYTHON_BIN` variable
set at install time to the bound interpreter path. This is a frozen snapshot of
the binding at the moment the launcher was generated.

## 3. Launcher Python Resolution

The launcher resolves the interpreter at runtime via the following cascade:

| Priority | Source | Rationale |
|----------|--------|-----------|
| 1 | Baked `PYTHON_BIN` in launcher script | Fastest path; direct install-time binding |
| 2 | `PYTHON_BINDING` text file | Fallback if baked path is stale (interpreter moved/upgraded) |
| 3 | **fail-closed** — exit 1 with clear error | No silent fallback to PATH probing |

### 3.1 Validation

At each priority level, the launcher checks whether the candidate path exists
and is executable. If not, it proceeds to the next priority.

### 3.2 Fail-Closed Behavior

If both baked path and `PYTHON_BINDING` fail validation, the launcher must:
- Print a clear error message identifying the expected interpreter path
- Exit with a non-zero exit code
- **Never** fall back to PATH-based probing (`python3`, `python`, `py -3`)

### 3.3 Environment Export

On successful resolution, the launcher exports `OPENCODE_PYTHON` as an
environment variable set to the resolved interpreter path. This provides
defense-in-depth for child processes.

## 4. Consumer Binding Rules

### 4.1 Launcher Scripts

**Location:** `${CONFIG_ROOT}/bin/opencode-governance-bootstrap` (Unix),
`${CONFIG_ROOT}/bin/opencode-governance-bootstrap.cmd` (Windows)

Launchers follow the resolution cascade from Section 3.

Launchers support subcommand routing:

| Subcommand | Target |
|------------|--------|
| `--session-reader [flags]` | `session_reader.py` with passthrough flags |
| `--ticket-persist [flags]` | `governance.entrypoints.phase4_intake_persist` (canonical public surface) |
| `--plan-persist [flags]` | `governance.entrypoints.phase5_plan_record_persist` (canonical public surface) |
| *(default)* | `governance.entrypoints.bootstrap_executor` |

### 4.1.1 Final launcher surface

Canonical subcommands for active operator workflows are:
- `--ticket-persist`
- `--plan-persist`
- `--session-reader`

### 4.2 Rails (Markdown Command Templates)

Rails invoke the launcher by its stable command name `opencode-governance-bootstrap`,
with an inline PATH prefix injected at install time:

**Unix (installed rail):**
```bash
PATH="<bin_dir>:$PATH" opencode-governance-bootstrap --session-reader --materialize
```

**Windows (installed rail):**
```cmd
set "PATH=<bin_dir>;%PATH%" && opencode-governance-bootstrap --session-reader --materialize
```

Rails are installed as platform-specific: the installer writes only the block
matching the target OS. Rails do **not** embed absolute Python paths.

### 4.3 Plugin (`audit-new-session.mjs`)

The plugin resolves the interpreter via the following cascade:

| Priority | Source | Rationale |
|----------|--------|-----------|
| 1 | `OPENCODE_PYTHON` environment variable | Explicit override / launcher-exported value |
| 2 | `PYTHON_BINDING` text file | Reads the install-time binding artifact |
| 3 | PATH probing (`python3`, `python`, `py -3`) | **Degraded fallback only** — when no installation binding exists (e.g., fresh clone without install) |

When priority 3 is used, the plugin should log a warning indicating that it is
operating without a binding and the result may differ from the installed interpreter.

### 4.4 Python Entrypoints (session_reader.py, etc.)

Self-bootstrapping entrypoints derive `commands_home` from their own filesystem
location (`Path(__file__).resolve().parents[2]`). They use whatever interpreter
started them — which is correct as long as the caller (launcher or plugin) uses
the bound interpreter.

No additional resolution logic is needed in entrypoints themselves.

## 5. Installer Responsibilities

### 5.1 Write Order

1. Write `governance.paths.json` (semantic SSOT)
2. Derive and write `PYTHON_BINDING` from `governance.paths.json:paths.pythonCommand`
3. Generate launcher scripts with baked `PYTHON_BIN`
4. Inject `{{BIN_DIR}}` into rail templates

### 5.2 Consistency Invariant

At the end of a successful install, the following must hold:

```
governance.paths.json:paths.pythonCommand
  == content of PYTHON_BINDING
  == PYTHON_BIN baked in launcher scripts
```

All three representations must refer to the same absolute interpreter path
(in POSIX-normalized form).

### 5.3 Re-Install / Update Behavior

On re-install, the installer re-derives all three artifacts from the current
`sys.executable` (or `OPENCODE_PYTHON` override). Stale values are overwritten.

## 6. Path Format

All interpreter paths in binding artifacts use POSIX-normalized absolute form:

| Platform | Example |
|----------|---------|
| Linux | `/usr/bin/python3` |
| macOS | `/opt/homebrew/bin/python3` |
| Windows | `C:/Users/dev/AppData/Local/Programs/Python/Python313/python.exe` |

Forward slashes on all platforms. OS-native conversion happens at consumption
time (e.g., `Path(binding_value)` in Python, which handles both separators).

## 7. Failure Modes and Reason Codes

| Condition | Behavior | Reason Code |
|-----------|----------|-------------|
| Bound interpreter missing (uninstalled/moved) | Launcher: try PYTHON_BINDING fallback, then fail-closed | — |
| PYTHON_BINDING file missing | Launcher: use baked path only, fail-closed if stale | — |
| PYTHON_BINDING file corrupt (empty/unreadable) | Treated as missing | — |
| Plugin: no binding artifacts found | Degraded fallback to PATH probing with warning | — |
| Plugin: binding exists but interpreter missing | Skip governance invocation with error log | — |

## 8. Relationship to Other Contracts

| Contract | Relationship |
|----------|-------------|
| `install-layout-contract.v_current` | Defines filesystem locations for `bin/`, `commands/`, `PYTHON_BINDING` |
| `opencode-integration-contract.v1` | Section 3 (Python Resolution Order) is **superseded** by this contract for installed environments. The integration contract's resolution table remains valid only as degraded fallback behavior. |
| `runtime-state-contract.v1` | No direct relationship |
