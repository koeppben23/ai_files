# Bootstrap Architecture - Before/After Comparison

This document describes the current (pre-change) behavior and the new behavior after removing AGENTS.md.

## Current Behavior (Before Change)

### With AGENTS.md Present

When AGENTS.md exists in the repository root:
- OpenCode host detects AGENTS.md as bootstrap evidence
- Chat enforces bootstrap completion before allowing work
- BLOCKED-START-REQUIRED if bootstrap not run
- Profile detection happens during bootstrap

**Windows Issue:** On Windows, chat-based bootstrap enforcement was unreliable due to subprocess handling issues.

### Without AGENTS.md

When AGENTS.md is missing:
- Bootstrap cannot proceed without alternative evidence
- Requires manual bootstrap via Python
- Users must run: `python3 install.py` then the local launcher

### Manual Python Bootstrap

The manual bootstrap process:
1. Run `python3 install.py` - installs governance files
2. Run the local launcher - triggers bootstrap
3. Bootstrap creates SESSION_STATE.json in workspace
4. Sets PersistenceCommitted, WorkspaceReadyGateCommitted flags

**Problem:** This relies on chat integration which is fragile on Windows.

### Windows-Specific Issues

- Subprocess spawning with `python` or `python3` often fails
- PATH resolution issues
- Requires explicit sys.executable but old code used generic python/python3
- [WinError 2] "File not found" common

## New Behavior (After Change)

### No AGENTS.md

AGENTS.md is removed entirely:
- No longer used as bootstrap evidence
- No longer copied during installation
- No longer checked in md_lint

### Local Launcher (New Standard)

The new bootstrap entry point:
- `~/.config/opencode/bin/opencode-governance-bootstrap` (Unix)
- `%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd` (Windows)

Benefits:
- Works on all platforms consistently
- Uses sys.executable for Python path
- Sets required environment variables
- No dependency on chat integration
- Fail-fast on missing config

### Installer Changes

The installer now:
- Creates `bin/` directory
- Generates Unix shell launcher
- Generates Windows cmd launcher
- Sets PYTHONPATH correctly
- Exports required env vars (OPENCODE_CONFIG_ROOT, COMMANDS_HOME)

### Smoketest

New `--smoketest` flag verifies:
- Launcher files exist
- governance.paths.json present
- cli.bootstrap importable

### Chat Behavior

Chat bootstrap is no longer required:
- Local launcher is the canonical entry point
- Chat should not be used to initiate bootstrap

## Migration Path

1. Install: `python3 install.py`
2. Bootstrap: `~/.config/opencode/bin/opencode-governance-bootstrap`
3. Verify: Check SESSION_STATE.json in workspace

## Key Differences

| Aspect | Old (AGENTS.md) | New (Launcher) |
|--------|-----------------|----------------|
| Entry point | Chat bootstrap | Local launcher |
| Windows support | Fragile | Reliable |
| Bootstrap enforcement | Chat-dependent | Standalone |
| AGENTS.md required | Yes | No |
| Profile detection | During chat bootstrap | During bootstrap |
