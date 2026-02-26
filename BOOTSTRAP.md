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

## Kernel Enforcement Notes

Bootstrap gates, evidence requirements, and blocked reasons are kernel-enforced via `governance/assets/config/bootstrap_policy.yaml`.

Discovery / Load search order (informational)
- `governance/assets/config/bootstrap_policy.yaml`

Fallback computed payloads remain debug-only (`nonEvidence`).
Helper output is operational convenience status only and is not canonical repo identity evidence.

## Response Contract Requirements

At session start, include exactly one start-mode banner based on discovery artifact validity evidence:
- `[START-MODE] Cold Start - reason:`
- `[START-MODE] Warm Start - reason:`

Include `[SNAPSHOT]` block (`Confidence`, `Risk`, `Scope`) with values aligned to current `SESSION_STATE`.

`SESSION_STATE` output MUST be formatted as fenced YAML (````yaml` + `SESSION_STATE:` payload)
`SESSION_STATE` output MUST NOT use placeholder tokens (`...`, `<...>`); use explicit unknown/null values instead

End every response with `[NEXT-ACTION]` footer (`Status`, `Next`, `Why`, `Command`) per `master.md` (also required in COMPAT mode)

If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`) when host constraints allow
If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `["none"]` if not command-driven) when host constraints allow.

If strict output formatting is host-constrained, response MUST include COMPAT sections: `RequiredInputs`, `Recovery`, and `NextAction` and set `DEVIATION.host_constraint = true`.
