# Bootstrap Guide

This document describes how to bootstrap the OpenCode Governance System for a repository.

## Overview

The OpenCode Governance System ensures consistent development practices across repositories. Before working in a repository, you must run the bootstrap process to activate governance.

## Bootstrap Process

The bootstrap process:

1. **Validates binding** - Checks `governance.paths.json` exists
2. **Detects repository** - Finds Git root and computes fingerprint
3. **Creates workspace** - Sets up `SESSION_STATE.json`
4. **Applies gates** - Ensures all required gates are satisfied

## Standard Bootstrap Path

The recommended way to bootstrap is using the **local launcher**:

### macOS / Linux

```bash
~/.config/opencode/bin/opencode-governance-bootstrap
```

### Windows

```cmd
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd
```

## Installation First

If the launcher is not available, run the installer first:

```bash
python3 install.py
```

This creates:
- Configuration directory at `~/.config/opencode`
- Commands and governance files
- Local bootstrap launcher
- Workspace directories

## Verification

After bootstrap, verify success by checking:

```bash
cat ~/.config/opencode/workspaces/<fingerprint>/SESSION_STATE.json
```

The file should contain:
- `Phase`: "4" or higher
- `Bootstrap.Satisfied`: `true`
- `PersistenceCommitted`: `true`

## Troubleshooting

### "Invalid or missing binding file"

Run the installer:
```bash
python3 install.py
```

### "Repository root not found"

Provide the repository path:
```bash
opencode-governance-bootstrap --repo-root /path/to/repo
```

Or ensure you're in a Git repository.

## Documentation

- `master.md` - Core governance rules
- `rules.md` - Implementation guidelines
- `profiles/` - Profile-specific rulebooks
