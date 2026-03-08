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

## Commands by platform

```bash
opencode-governance-bootstrap
```

```powershell
opencode-governance-bootstrap
```

### Optional flags

```bash
opencode-governance-bootstrap --repo-root /path/to/repo --config-root /path/to/opencode-config
```

```powershell
opencode-governance-bootstrap --repo-root C:\path\to\repo --config-root C:\path\to\opencode-config
```

## If execution is unavailable

If the bootstrap command cannot be executed, ask the user to verify that the installer
has been run and that the launcher is on `PATH`.

## Repository root not found

If the bootstrap command reports "Repository root not found":

- verify you are inside the target repository
- rerun from the repository root
- if needed, provide the repository root path explicitly via `--repo-root`
