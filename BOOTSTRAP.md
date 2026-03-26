<!-- rail-classification: MUTATING, BOOTSTRAP -->

# Governance Bootstrap

## Purpose

`opencode-governance-bootstrap` initializes or resumes a governance session for the current repository.
It creates the session state file, writes the initial audit event, and prepares the governance environment.
This launcher-first command is the only canonical operator bootstrap path.
`python -m ...` invocation is internal/debug/compatibility-only and not primary user guidance.

## Installation

If the launcher is not available, run the installer first:

```bash
# macOS / Linux (from extracted bundle)
./install/install.sh
```

```powershell
# Windows (from extracted bundle)
.\install\install.ps1
```

This creates the launcher wrapper and adds it to the configured binary directory.

> **Note:** The installer places the launcher at `~/.config/opencode/bin/` (macOS/Linux) or
> `%USERPROFILE%\.config\opencode\bin\` (Windows). It is **not** added to your shell PATH
> automatically. Either add the directory to PATH or use the full path when invoking the launcher.
> See `QUICKSTART.md` Step 3 for detailed instructions.

## Commands by platform

### With PATH configured

```bash
# macOS / Linux (bash / zsh)
export PATH="$HOME/.config/opencode/bin:$PATH"
opencode-governance-bootstrap init --profile solo --repo-root /path/to/repo
```

```powershell
# Windows (PowerShell)
$env:Path = "$env:USERPROFILE\.config\opencode\bin;" + $env:Path
opencode-governance-bootstrap init --profile solo --repo-root C:\path\to\repo
```

```cmd
:: Windows (cmd.exe)
set "PATH=%USERPROFILE%\.config\opencode\bin;%PATH%"
opencode-governance-bootstrap.cmd init --profile solo --repo-root C:\path\to\repo
```

### Without PATH — invoke by full path

```bash
# macOS / Linux (bash / zsh)
~/.config/opencode/bin/opencode-governance-bootstrap init --profile solo --repo-root /path/to/repo
```

```powershell
# Windows (PowerShell)
& "$env:USERPROFILE\.config\opencode\bin\opencode-governance-bootstrap.cmd" init --profile solo --repo-root C:\path\to\repo
```

```cmd
:: Windows (cmd.exe)
"%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd" init --profile solo --repo-root C:\path\to\repo
```

### Optional flags

```bash
opencode-governance-bootstrap init --profile team --repo-root /path/to/repo --config-root /path/to/opencode-config
```

```powershell
opencode-governance-bootstrap init --profile team --repo-root C:\path\to\repo --config-root C:\path\to\opencode-config
```

```cmd
opencode-governance-bootstrap.cmd init --profile team --repo-root C:\path\to\repo --config-root C:\path\to\opencode-config
```

## Install/layout truth

- Config root (default): `~/.config/opencode`
  - `commands/`, `plugins/`, `workspaces/`, `bin/`
- Local root (default): `~/.local/share/opencode`
  - `governance_runtime/`, `governance_content/`, `governance_spec/`, `governance/`, `VERSION`
- Workspace files: `~/.config/opencode/workspaces/<repo_fingerprint>/`
  - `governance-config.json` — policy knobs (automatically materialized during bootstrap)
  - `SESSION_STATE.json` — current session state
  - `logs/` — workspace logs
- Global logs: `~/.config/opencode/workspaces/_global/logs/`

### Operating mode setup surface

- Canonical setup path: `init --profile <solo|team|regulated>`
- Optional alias (administrative): `--set-operating-mode <solo|team|regulated>`

On success, bootstrap prints:

- `repoOperatingMode = <profile>`
- `resolvedOperatingMode default = <profile>`
- `policyPath = <repo>/.opencode/governance-repo-policy.json`

## If execution is unavailable

If the bootstrap command cannot be executed, ask the user to verify that the installer
has been run and that the launcher is on `PATH`.

## Repository root not found

If the bootstrap command reports "Repository root not found":

- verify you are inside the target repository
- rerun from the repository root
- if needed, provide the repository root path explicitly via `--repo-root`
