## Step 1: Install (2 minutes)

```bash
# Extract the customer install bundle
unzip customer-install-bundle-v1.zip
cd customer-install-bundle-v1

# Run installer (macOS / Linux)
./install/install.sh
```

```powershell
# Windows (PowerShell)
Expand-Archive -Path customer-install-bundle-v1.zip -DestinationPath .
cd customer-install-bundle-v1
.\install\install.ps1
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

After bootstrap succeeds, open OpenCode Desktop in the same repository and run `/continue`.
If the command cannot be executed, the model asks the user to paste the command output.
For rail details and lifecycle behavior, use `README-OPENCODE.md`.

## Output Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

Further reading: `README-OPENCODE.md`, `README.md`.
