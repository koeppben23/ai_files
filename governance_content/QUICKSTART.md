SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance_runtime/kernel/*` is the canonical control-plane implementation.
Legacy bridge note: `governance/kernel/*` is compatibility surface only.
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
opencode-governance-bootstrap init --profile solo --repo-root /path/to/repo
```

```powershell
# Windows (PowerShell)
opencode-governance-bootstrap init --profile solo --repo-root C:\path\to\repo
```

```cmd
:: Windows (cmd.exe)
opencode-governance-bootstrap.cmd init --profile solo --repo-root C:\path\to\repo
```

Profiles: `solo`, `team`, `regulated`.

Optional alias (administrative surface, same semantics):

```bash
opencode-governance-bootstrap --set-operating-mode solo --repo-root /path/to/repo
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
If you choose `changes_requested`, the workflow enters `Rework Clarification Gate`; clarify requested changes in chat, then run exactly one directed rail (`/ticket`, `/plan`, or `/continue`).
If you choose `reject`, the workflow returns to the Ticket Input Gate; primary next action is `/ticket` with updated scope.
Alternative: run `/review` for read-only feedback before re-entering the development path.
If the command cannot be executed, the model asks the user to paste the command output.
For rail details and lifecycle behavior, use `README-OPENCODE.md`.

## Output Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `BLOCKED-MISSING-BINDING-FILE` | Install not run | Rerun the installer from the bundle |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository not found | Provide `--repo-root` |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Bootstrap failed | Check logs |

Further reading: `README-OPENCODE.md`, `README.md`.
