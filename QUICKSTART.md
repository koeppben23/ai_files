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

# Windows
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\your-repo
```

**Expected output:**

| Error | Fix |
|-------|-----|
| Launcher not found | Run the installer from the bundle first |
| Binding file invalid | Rerun the installer from the bundle |
| Repo not detected | Provide `--repo-root /path/to/repo` |
| Not a Git repository | Initialize git or provide `--repo-root` to a valid Git repo |

## Step 3: First Governed Task (2 minutes)

| Command | Purpose |
|---------|---------|
| `~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /abs/path/to/repo` | Bootstrap session (required) |
| `%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\repo` | Bootstrap session (Windows) |
| `/continue` | Resume active session |
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
/continue
"Implement now"
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

### macOS / Linux

- Use `~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /absolute/path/to/your-repo`

## Understanding the Output


| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

### Phase Progress

## Next Steps

1. **Bootstrap guide**: [BOOTSTRAP.md](BOOTSTRAP.md)
2. **Understand phases**: [docs/phases.md](docs/phases.md)
3. **Security model**: [docs/security-gates.md](docs/security-gates.md)
4. **Install layout**: [docs/install-layout.md](docs/install-layout.md)
5. **Governance invariants**: [docs/governance_invariants.md](docs/governance_invariants.md)

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
SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
