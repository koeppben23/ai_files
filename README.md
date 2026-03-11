## What this bundle provides

- Deterministic governance workflow (Phases 1-6) with explicit gate outcomes.
- Installer-managed runtime and policy assets under `governance/`.
- OpenCode launcher and command surfaces for governed session execution.
- Profile and addon support under `profiles/`.

## Install

```bash
unzip customer-install-bundle-v1.zip
cd customer-install-bundle-v1
./install/install.sh
```

```powershell
Expand-Archive -Path customer-install-bundle-v1.zip -DestinationPath .
cd customer-install-bundle-v1
.\install\install.ps1
```

## Verify

```bash
./install/install.sh --status
./install/install.sh --smoketest
```

```powershell
.\install\install.ps1 --status
.\install\install.ps1 --smoketest
```

`governance.paths.json` under `<config_root>/commands/` is required for canonical bootstrap behavior.

## Start a governed session

### Prerequisites: make the launcher reachable

The installer places the launcher at `~/.config/opencode/bin/` (macOS/Linux) or
`%USERPROFILE%\.config\opencode\bin\` (Windows). It is **not** added to PATH automatically.

Either add the directory to PATH once per shell session, or invoke the launcher by its full path.

**Add to PATH (run once per shell session):**

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

### Run bootstrap

After PATH is set (or using the full path), run the canonical setup command:

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

Optional administrative alias (same behavior):

```bash
opencode-governance-bootstrap --set-operating-mode solo --repo-root /path/to/repo
```

**Without PATH — invoke by full path:**

```bash
~/.config/opencode/bin/opencode-governance-bootstrap init --profile solo --repo-root /path/to/repo
```

```powershell
& "$env:USERPROFILE\.config\opencode\bin\opencode-governance-bootstrap.cmd" init --profile solo --repo-root C:\path\to\repo
```

```cmd
"%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd" init --profile solo --repo-root C:\path\to\repo
```

### Continue in OpenCode

1. Open OpenCode Desktop in the same repository and run `/continue`.
2. For new work at Phase 4, run `/ticket`, then `/plan`; alternatively run `/review` for read-only review feedback (no state change).
3. Use `/review` as a read-only rail entrypoint for review-depth feedback.
4. At Phase 6 Evidence Presentation Gate, run `/review-decision <approve|changes_requested|reject>` (for example `/review-decision approve`).
5. If you choose `changes_requested`, the workflow enters `Rework Clarification Gate`; clarify requested changes in chat first, then run exactly one directed rail (`/ticket`, `/plan`, or `/continue`).
6. If you choose `reject`, the workflow returns to Phase 4 Ticket Input Gate; primary next action is `/ticket` with updated scope (alternative: `/review` for read-only feedback).
7. If you choose `approve`, run `/implement` to persist the governance-to-implementation handoff before starting repository changes.

## Docs and troubleshooting

- OpenCode lifecycle: `README-OPENCODE.md`
- Quickstart: `QUICKSTART.md`
- Rules overview: `README-RULES.md`
- Install path binding details: `docs/install-layout.md`

## Uninstall

Current stable public uninstall surface:

```bash
python install.py --uninstall --force
```

This is the currently supported remove operation until bundle-level uninstall surface is explicitly marked stable.

Uninstall removes installer-owned governance files and runtime state, and preserves:
- opencode.json
- `governance.paths.json` (unless `--purge-paths-file` is passed)
- Non-governance user-owned files
