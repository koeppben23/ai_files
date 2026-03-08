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

## Step 2: Verify installation

```bash
# macOS / Linux
./install/install.sh --status
```

```powershell
# Windows
.\install\install.ps1 --status
```

## Step 3: Bootstrap session (1 minute)

```bash
# macOS / Linux
opencode-governance-bootstrap --repo-root <repo-root>
```

```powershell
# Windows
opencode-governance-bootstrap.cmd --repo-root <repo-root>
```

Use `--verbose` for step-by-step bootstrap output.

| Error | Fix |
|-------|-----|
| Launcher not found | Run the installer from the bundle first |
| Repo not detected | Provide `--repo-root /path/to/repo` |

## Step 4: Open Desktop and continue

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
opencode-governance-bootstrap --repo-root <repo-root>
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

**Debug blocked run:**
```bash
# macOS / Linux
cat "${CONFIG_ROOT}/commands/logs/error.log.jsonl"
```

```powershell
# Windows
Get-Content "$env:CONFIG_ROOT\commands\logs\error.log.jsonl"
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
