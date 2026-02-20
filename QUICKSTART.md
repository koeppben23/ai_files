# Quick Start: 5-Minute Governance Setup

Get deterministic, auditable AI-assisted development in under 5 minutes.

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

In OpenCode (or compatible LLM frontend):

```
/start
```

**Expected output:**
```
[START-MODE] Cold Start - reason: no existing workspace cache
[PHASE-1.1-COMPLETE]
Bootstrap Evidence:
  Binding: governance.paths.json ✓
  Preflight: git ✓, python3 ✓
  Repo Identity: git@github.com:org/repo.git (main)
```

**Note:** Workspace persistence (fingerprint folder, SESSION_STATE.json) requires the host to set `OPENCODE_DIAGNOSTICS_ALLOW_WRITE=1`. Without this, the preflight runs in read-only mode and persistence is deferred.

### Troubleshooting Step 2

| Error | Fix |
|-------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Run `python3 install.py` |
| `BLOCKED-VARIABLE-RESOLUTION` | Check `~/.config/opencode/commands/governance.paths.json` |
| `BLOCKED-REPO-IDENTITY` | Ensure you're in a git repository |
| Workspace not persisted | Host must set `OPENCODE_DIAGNOSTICS_ALLOW_WRITE=1` for persistence; or run manually: `OPENCODE_DIAGNOSTICS_ALLOW_WRITE=1 python3 diagnostics/bootstrap_session_state.py --repo-fingerprint <fp>` |

## Step 3: First Governed Task (2 minutes)

After `/start` completes, provide a task:

```
Implement a function to validate email addresses with tests
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
| `/start` | Bootstrap governance session |
| `/continue` | Resume active session |
| `python3 install.py` | Install/update governance |
| `python3 install.py --status` | Check installation |
| `python3 scripts/audit_explain.py --last` | Explain last run |

### Common Workflows

**Start new work:**
```
/start
<describe task>
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

**Check why something was blocked:**
```bash
python3 scripts/audit_explain.py --run <run_id>
```

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
| `BLOCKED-START-REQUIRED` | Session not bootstrapped | `/start` |
| `BLOCKED-MISSING-EVIDENCE` | Required evidence missing | Check payload for details |
| `INTERACTIVE-REQUIRED-IN-PIPELINE` | CI needs user input | Add pre-approved config |

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
3. **Security model**: [docs/security-gates.md](docs/security-gates.md)
4. **Stability contract**: [STABILITY_SLA.md](STABILITY_SLA.md)

## Getting Help

1. Run `python3 scripts/audit_explain.py --last` for diagnostics
2. Check [docs/governance_invariants.md](docs/governance_invariants.md)
3. Review reason code mapping: `diagnostics/REASON_REMEDIATION_MAP.json`

## Verification Checklist

After setup, verify:

- [ ] `python3 install.py --status` shows OK
- [ ] `/start` completes without blockers
- [ ] Phase 2 discovery shows correct profile
- [ ] Can provide a task and see plan output

---

**Time to first governed PR: < 5 minutes**
