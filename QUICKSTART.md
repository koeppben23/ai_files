SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.

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

The installer places the `opencode-governance-bootstrap` launcher in a platform-specific config directory.
Add that directory to your shell PATH, then invoke the launcher by name.

### Set PATH (run once per shell session)

```bash
# macOS / Linux (bash / zsh)
export PATH="$HOME/.config/opencode/bin:$PATH"
```

```powershell
# Windows (PowerShell)
$env:Path = "$env:USERPROFILE\.config\opencode\bin;" + $env:Path
```

```cmd
:: Windows (cmd.exe)
set "PATH=%USERPROFILE%\.config\opencode\bin;%PATH%"
```

### Run the bootstrap

```bash
# macOS / Linux
opencode-governance-bootstrap --repo-root /path/to/repo
```

```powershell
# Windows (PowerShell)
opencode-governance-bootstrap --repo-root C:\path\to\repo
```

```cmd
:: Windows (cmd.exe)
opencode-governance-bootstrap.cmd --repo-root C:\path\to\repo
```

Use `--verbose` for step-by-step bootstrap output.

| Error | Fix |
|-------|-----|
| Launcher not found | Run the installer from the bundle first |
| Repo not detected | Provide `--repo-root /path/to/repo` |
| `opencode-governance-bootstrap` is not recognized | The launcher is not on PATH — set PATH as shown above |

## Step 4: Open Desktop and continue

After bootstrap succeeds, open OpenCode Desktop in the same repository and run `/continue`.
If `/continue` lands in Phase 4, run `/ticket` and then `/plan`; alternatively run `/review` for read-only review feedback (no state change).
Use `/review` as a read-only rail entrypoint for quality feedback. At Phase 6, run `/review-decision <approve|changes_requested|reject>` for the final decision.
If you choose `changes_requested`, continue through a controlled Phase-6 correction loop after clarifying what failed and what must change.
If you choose `reject`, the workflow returns to Phase 4 Ticket Input Gate; restart with `/ticket` and updated scope.
If the command cannot be executed, the model asks the user to paste the command output.
For rail details and lifecycle behavior, use `README-OPENCODE.md`.

## Output Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

Further reading: `README-OPENCODE.md`, `README.md`.
