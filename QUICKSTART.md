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

| Error | Fix |
|-------|-----|
| Permission denied | Run with appropriate permissions or use `--user` flag |
| Path not found | Ensure the bundle directory exists and is extracted |
| Binding file missing | Rerun the installer from the bundle |

## Step 2: Bootstrap Session (1 minute)

```bash
# macOS / Linux
~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo
```

```powershell
# Windows
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\your-repo
```

Use `--verbose` for step-by-step bootstrap output.
If the desktop plugin cannot find Python in `PATH`, set `OPENCODE_PYTHON` to the full interpreter path.

| Error | Fix |
|-------|-----|
| Launcher not found | Run the installer from the bundle first |
| Repo not detected | Provide `--repo-root /path/to/repo` |

## Step 3: Open Desktop and Continue

After bootstrap succeeds, open OpenCode Desktop in the same repository and start with `/continue`.
If `/continue` lands at Phase 4 (Ticket Intake), enter Plan Mode first for every new ticket/task.
Use `/review` as a read-only rail entrypoint for lead/staff depth feedback.
If the command cannot be executed, the model asks the user to paste the command output.

| Command | Purpose |
|---------|---------|
| `/continue` | Standard Desktop entrypoint after bootstrap |
| `/review` | Read-only rail entrypoint for lead/staff PR/ticket feedback |
| `/ticket` | Persist ticket/task intake evidence |
| `/plan` | Persist Phase-5 plan-record evidence |
| `/audit-readout` | Read-only audit snapshot (`AUDIT_READOUT_SPEC.v1`) |

### Common Workflows

**Start new work:**
```bash
~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo
# Open OpenCode Desktop
/continue
# If /continue lands at Phase 4 (Ticket Intake), enter Plan Mode first
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
~/.config/opencode/bin/opencode-governance-bootstrap --entrypoint governance.entrypoints.new_work_session --trigger-source pipeline --reason "nightly run" --quiet
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

## Output Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

## Next Steps

1. **Bootstrap guide**: [BOOTSTRAP.md](BOOTSTRAP.md)
2. **Understand phases**: [docs/phases.md](docs/phases.md)
3. **Operator runbook**: [docs/operator-runbook.md](docs/operator-runbook.md)

For upgrade, rollback, and advanced operations, see the [Operator Runbook](docs/operator-runbook.md).

---
SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.
