## Step 1: Install (2 minutes)

```bash
# Extract the customer install bundle
unzip customer-install-bundle-v1.zip
cd customer-install-bundle-v1

# Run installer (macOS / Linux)
./install/install.sh

# Verify installation
./install/install.sh --status
```

```powershell
# Windows (PowerShell)
Expand-Archive -Path customer-install-bundle-v1.zip -DestinationPath .
cd customer-install-bundle-v1
.\install\install.ps1

# Verify installation
.\install\install.ps1 --status
```

**Expected output:**
| Error | Fix |
|-------|-----|
| Permission denied | Run with appropriate permissions or use `--user` flag |
| Path not found | Ensure the bundle directory exists and is extracted |
| Binding file missing | Rerun the installer from the bundle |

## Step 2: Bootstrap Session (1 minute)


```bash
# macOS / Linux
~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo

# Optional: verbose bootstrap flow
~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo --verbose

# Windows
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\your-repo

# Optional: verbose bootstrap flow
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\your-repo --verbose
```

**Expected output:**

| Error | Fix |
|-------|-----|
| Launcher not found | Run the installer from the bundle first |
| Binding file invalid | Rerun the installer from the bundle |
| Repo not detected | Provide `--repo-root /path/to/repo` |
| Not a Git repository | Initialize git or provide `--repo-root` to a valid Git repo |

## Step 3: Open Desktop and Continue (2 minutes)

After bootstrap succeeds, open OpenCode Desktop in the same repository and start with `/continue`.
This reuses the persisted session state from bootstrap and avoids duplicate initialization.
If `/continue` lands at Phase 4 (Ticket Intake), start in Plan Mode for every new ticket/task.
Use `/review` as a read-only rail entrypoint for lead/staff depth feedback (no implementation).
If the model cannot execute the session-reader command (e.g., sandboxed environment), it will ask you to paste the command output or proceed with conversation context only.

| Command | Purpose |
|---------|---------|
| `~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /abs/path/to/repo` | Bootstrap session (required) |
| `%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\repo` | Bootstrap session (Windows) |
| `/continue` | Standard Desktop entrypoint after bootstrap |
| `/audit-readout` | Read-only audit snapshot (`AUDIT_READOUT_SPEC.v1`) |
| `python3 -m governance.entrypoints.new_work_session --trigger-source cli --quiet` | Start a fresh Phase-4 work run in the same repo |
| `python3 scripts/governance_session_new.py --trigger-source pipeline --quiet` | Pipeline wrapper for fresh Phase-4 work run |
| `/review` | Read-only rail entrypoint for lead/staff PR/ticket feedback |
| `/ticket` | Persist ticket/task intake evidence and reroute from Phase 4 |
| `/plan` | Persist Phase-5 plan-record evidence before architecture review |
| `./install/install.sh` | Install/update governance (macOS/Linux, from bundle) |
| `./install/install.sh --status` | Check installation (macOS/Linux, from bundle) |
| `./install/install.sh --smoketest` | Run installation smoketest (macOS/Linux, from bundle) |
| `.\install\install.ps1` | Install/update governance (Windows, from bundle) |
| `.\install\install.ps1 --status` | Check installation (Windows, from bundle) |
| `.\install\install.ps1 --smoketest` | Run installation smoketest (Windows, from bundle) |

### Common Workflows

**Start new work:**
```bash
~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo
# Open OpenCode Desktop in /absolute/path/to/your-repo
# Desktop New Session triggers ~/.config/opencode/plugins/audit-new-session.mjs (global plugin)
/continue
# If /continue lands at Phase 4 (Ticket Intake), enter Plan Mode first
# Provide ticket/task text in chat
"<ticket/task text>"
/ticket
# Persist Phase-5 plan record when the gate asks for it
/plan
# Plan Mode continues until plan is approved; then exit Plan Mode
/review
# After P5 gates are approved: implement changes
```

```bash
# Non-interactive new work run (CLI/Pipeline)
python3 -m governance.entrypoints.new_work_session --trigger-source pipeline --reason "nightly run" --quiet
/continue
```

**Debug a blocked run:**
```bash
# macOS / Linux
cat ~/.config/opencode/commands/logs/error.log.jsonl
```

```powershell
# Windows
Get-Content "$env:USERPROFILE\.config\opencode\commands\logs\error.log.jsonl"
```

## Platform Notes

### Windows

- Always use the local launcher: `%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\your-repo`
- The launcher uses the correct Python interpreter from installation
- If the desktop plugin cannot find Python in `PATH`, set `OPENCODE_PYTHON` to the full interpreter path (for example `C:\Python313\python.exe`)

### macOS / Linux

- Use `~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo`

## Understanding the Output


| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

### Phase Progress

## Upgrading Governance

For detailed upgrade/rollback procedures, see the
[Operator Runbook](docs/operator-runbook.md).

### Quick Upgrade

```bash
# 1. Pre-upgrade health check
python scripts/validate_rulebook.py --all \
  && python scripts/governance_lint.py \
  && python scripts/migrate_rulebook_schema.py --check

# 2. Backup
cp -r rulesets/ rulesets.bak/

# 3. Dry run
python scripts/migrate_rulebook_schema.py --dry-run

# 4. Apply migration
python scripts/migrate_rulebook_schema.py --target-version <VERSION>

# 5. Post-upgrade verification
python scripts/validate_rulebook.py --all \
  && python scripts/governance_lint.py \
  && python scripts/migrate_rulebook_schema.py --check
```

### Quick Rollback

If post-upgrade verification fails:

```bash
cp -r rulesets.bak/ rulesets/
python scripts/migrate_rulebook_schema.py --check
```

Current rollback depth: **1 level** (engine pointer swap).

## Next Steps

1. **Bootstrap guide**: [BOOTSTRAP.md](BOOTSTRAP.md)
2. **Understand phases**: [docs/phases.md](docs/phases.md)
3. **Security model**: [docs/security-gates.md](docs/security-gates.md)
4. **Install layout**: [docs/install-layout.md](docs/install-layout.md)
5. **Governance invariants**: [docs/governance_invariants.md](docs/governance_invariants.md)
6. **Operator runbook**: [docs/operator-runbook.md](docs/operator-runbook.md)

## Getting Help

1. Check [docs/governance_invariants.md](docs/governance_invariants.md)
2. Review reason code mapping: `~/.config/opencode/commands/governance/REASON_REMEDIATION_MAP.json`
3. Inspect error logs: `~/.config/opencode/commands/logs/error.log.jsonl`

## Verification Checklist

After setup, verify:

- [ ] Bundle installer (`install.sh` or `install.ps1`) `--status` shows OK
- [ ] Bundle installer (`install.sh` or `install.ps1`) `--smoketest` passes
- [ ] Local bootstrap launcher runs without errors when invoked with `--repo-root`
- [ ] Phase 2 discovery shows correct profile

---
SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.
