# Quick Start: 5-Minute Governance Setup

Get deterministic, auditable AI-assisted development in under 5 minutes.

SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.

## Prerequisites

| Requirement | Check | Install |
|-------------|-------|---------|
| Python 3.9+ | `python3 --version` | [python.org](https://python.org) |
| Git | `git --version` | [git-scm.com](https://git-scm.com) |

## Step 1: Install (2 minutes)

```bash
# Clone or navigate to governance repo
cd /path/to/ai_files

# Run installer
python3 install.py

# Verify installation
python3 install.py --status
```

**Expected output:**
```
Installation Status: OK
Config Root: ~/.config/opencode
Binding File: ~/.config/opencode/commands/governance.paths.json
```

### Troubleshooting Step 1

| Error | Fix |
|-------|-----|
| Permission denied | Run with appropriate permissions or use `--user` flag |
| Path not found | Ensure parent directory exists |
| Binding file missing | Rerun `python3 install.py` |

## Step 2: Bootstrap Session (1 minute)

Run the local bootstrap launcher:

```bash
# macOS / Linux
~/.config/opencode/bin/opencode-governance-bootstrap

# Windows
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd
```

Or from within a Git repository, simply:

```bash
cd /path/to/your-repo
~/.config/opencode/bin/opencode-governance-bootstrap
```

**Expected output:**
```
OpenCode Governance Bootstrap Launcher
====================================
Config root: /Users/.../.config/opencode
Commands home: /Users/.../.config/opencode/commands
Repo root: /Users/.../your-repo
Repo fingerprint: abc123...
Repo name: your-repo
...
```

### Troubleshooting Step 2

| Error | Fix |
|-------|-----|
| Launcher not found | Run `python3 install.py` first |
| Binding file invalid | Run `python3 install.py` to regenerate |
| Repo not detected | Provide `--repo-root /path/to/repo` or run from within Git repo |
| Not a Git repository | Initialize git or provide `--repo-root` to a valid Git repo |

## Step 3: First Governed Task (2 minutes)

After bootstrap completes, you can work in OpenCode:

```
/continue
```

The governance system will:
1. Detect your stack (Python, Java, etc.)
2. Load appropriate profile
3. Create a plan (Phase 4-5)
4. Generate code with evidence
5. Run quality gates (Phase 6)

## Quick Reference

### Essential Commands

| Command | Purpose |
|---------|---------|
| `~/.config/opencode/bin/opencode-governance-bootstrap` | Bootstrap session (recommended) |
| `/start` | Optional convenience path (delegates to bootstrap) |
| `/continue` | Resume active session |
| `python3 install.py` | Install/update governance |
| `python3 install.py --status` | Check installation |
| `python3 install.py --smoketest` | Run installation smoketest |

### Common Workflows

**Start new work:**
```bash
~/.config/opencode/bin/opencode-governance-bootstrap
/continue
"Implement now"
```

**Resume paused work:**
```
/continue
```

**Debug a blocked run:**
```bash
python3 scripts/audit_explain.py --last
```

## Platform Notes

### Windows

- Always use the local launcher: `%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd`
- Do not rely on `/start` in chat for Windows
- The launcher uses the correct Python interpreter from installation

### macOS / Linux

- Use `~/.config/opencode/bin/opencode-governance-bootstrap`
- Chat `/start` may work if the host supports it

## Understanding the Output

### Status Tags

| Status | Meaning |
|--------|---------|
| `OK` | Gate passed, proceeding |
| `BLOCKED` | Missing evidence or gate failed |
| `WARN` | Advisory issue, not blocking |
| `NOT_VERIFIED` | Claim lacks evidence |

### Reason Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | `python3 install.py` |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` or run from Git repo |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

### Phase Progress

```
[##----] 2/6
```

| Phase | Name | Purpose |
|-------|------|---------|
| 1 | Bootstrap | Preflight, identity |
| 2 | Discovery | Repo analysis, profile detection |
| 3 | API Validation | Contract validation (if applicable) |
| 4 | Planning | Architecture, test strategy |
| 5 | Implementation | Code generation, gates |
| 6 | QA | Quality verification, PR-ready |

## Configuration

### Mode Selection

| Mode | Use Case | Prompts |
|------|----------|---------|
| `user` | Local development | 100 |
| `pipeline` | CI/CD | 0 (silent) |
| `architect` | Plan-only | 50 |
| `implement` | Code generation | 150 |

### Profile Detection

Automatic based on repo signals:

| Signal | Profile |
|--------|---------|
| `*.py`, `requirements.txt` | `backend-python` |
| `pom.xml`, `build.gradle` | `backend-java` |
| `angular.json`, `nx.json` | `frontend-angular-nx` |
| No match | `fallback-minimum` |

## Next Steps

1. **Read the rules**: [README-RULES.md](README-RULES.md)
2. **Understand phases**: [docs/phases.md](docs/phases.md)
3. **Bootstrap guide**: [BOOTSTRAP.md](BOOTSTRAP.md)
4. **Security model**: [docs/security-gates.md](docs/security-gates.md)
5. **Stability contract**: [STABILITY_SLA.md](STABILITY_SLA.md)

## Getting Help

1. Run `python3 scripts/audit_explain.py --last` for governance
2. Check [docs/governance_invariants.md](docs/governance_invariants.md)
3. Review reason code mapping: `governance/REASON_REMEDIATION_MAP.json`

## Verification Checklist

After setup, verify:

- [ ] `python3 install.py --status` shows OK
- [ ] `python3 install.py --smoketest` passes
- [ ] Local bootstrap launcher runs without errors
- [ ] Phase 2 discovery shows correct profile

---

**Time to first governed PR: < 5 minutes**
