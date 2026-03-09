<!-- rail-classification: MUTATING, BOOTSTRAP -->

# Governance Bootstrap

## Purpose

`opencode-governance-bootstrap` initializes or resumes a governance session for the current repository.
It creates the session state file, writes the initial audit event, and prepares the governance environment.

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
opencode-governance-bootstrap
```

```powershell
# Windows (PowerShell)
$env:Path = "$env:USERPROFILE\.config\opencode\bin;" + $env:Path
opencode-governance-bootstrap
```

```cmd
:: Windows (cmd.exe)
set "PATH=%USERPROFILE%\.config\opencode\bin;%PATH%"
opencode-governance-bootstrap.cmd
```

### Without PATH — invoke by full path

```bash
# macOS / Linux (bash / zsh)
~/.config/opencode/bin/opencode-governance-bootstrap
```

```powershell
# Windows (PowerShell)
& "$env:USERPROFILE\.config\opencode\bin\opencode-governance-bootstrap.cmd"
```

```cmd
:: Windows (cmd.exe)
"%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd"
```

### Optional flags

```bash
opencode-governance-bootstrap --repo-root /path/to/repo --config-root /path/to/opencode-config
```

```powershell
opencode-governance-bootstrap --repo-root C:\path\to\repo --config-root C:\path\to\opencode-config
```

```cmd
opencode-governance-bootstrap.cmd --repo-root C:\path\to\repo --config-root C:\path\to\opencode-config
```

## If execution is unavailable

If the bootstrap command cannot be executed, ask the user to verify that the installer
has been run and that the launcher is on `PATH`.

## Repository root not found

If the bootstrap command reports "Repository root not found":

- verify you are inside the target repository
- rerun from the repository root
- if needed, provide the repository root path explicitly via `--repo-root`
