
## OpenCode Lifecycle

Back to install and bundle overview: `README.md`.

- Bootstrap: Use local launcher (`~/.config/opencode/bin/opencode-governance-bootstrap --repo-root /abs/path/to/repo`)
- Windows launcher: `%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd --repo-root C:\path\to\repo`
- After bootstrap, open OpenCode Desktop in the same repo and run `/continue`
- At Phase 4 (Ticket Intake Gate), enter Plan Mode first for any new ticket/task
- `/resume`: continue an interrupted session deterministically
- `/audit`: read-only governance report flow

Runtime persistence is repo-scoped under `${WORKSPACES_HOME}/<repo_fingerprint>/...` with a global active pointer at `${SESSION_STATE_POINTER_FILE}`.

Note: The commands below reference files installed under `${COMMANDS_HOME}` by the bundle installer.

Operational helpers:

```bash
# macOS / Linux
${PYTHON_COMMAND} ~/.config/opencode/commands/governance/entrypoints/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>
${PYTHON_COMMAND} ~/.config/opencode/commands/governance/entrypoints/persist_workspace_artifacts.py --repo-root <repo_path>
${PYTHON_COMMAND} ~/.config/opencode/commands/scripts/migrate_session_state.py --workspace <repo_fingerprint>
```

```powershell
# Windows
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\governance\entrypoints\bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\governance\entrypoints\persist_workspace_artifacts.py --repo-root <repo_path>
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\scripts\migrate_session_state.py --workspace <repo_fingerprint>
```

Use `--dry-run` when validating changes before writing.
## 60-Second OpenCode Verification

```bash
# macOS / Linux
./install/install.sh --status
${PYTHON_COMMAND} ~/.config/opencode/commands/governance/entrypoints/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --dry-run
```

```powershell
# Windows
.\install\install.ps1 --status
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\governance\entrypoints\bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --dry-run
```

Then run the local bootstrap launcher and confirm bootstrap succeeds without binding/identity blockers.
Response rendering quick check:

```bash
# macOS / Linux
${PYTHON_COMMAND} ~/.config/opencode/commands/scripts/render_response_envelope.py --input response.json --format markdown
${PYTHON_COMMAND} ~/.config/opencode/commands/scripts/render_response_envelope.py --input response.json --format plain
${PYTHON_COMMAND} ~/.config/opencode/commands/scripts/render_response_envelope.py --input response.json --format json
```

```powershell
# Windows
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\scripts\render_response_envelope.py --input response.json --format markdown
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\scripts\render_response_envelope.py --input response.json --format plain
${PYTHON_COMMAND} $env:USERPROFILE\.config\opencode\commands\scripts\render_response_envelope.py --input response.json --format json
```

`--format auto` is the default and resolves to plain for interactive TTY sessions (stable across Windows/macOS/Linux terminals) and JSON for non-interactive execution.

## Troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun the bundle installer, then verify with `--status`.
- `BLOCKED-VARIABLE-RESOLUTION`: validate config-root/path binding resolution (`docs/install-layout.md`).
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure current directory is a git repo and `git` is available in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE` or `NOT_VERIFIED-EVIDENCE-STALE`: refresh/provide evidence and rerun.

## Uninstall and State Cleanup

Uninstall removes all governance runtime state in addition to installed files.

**Important:** opencode.json is **never** deleted on uninstall. It is user/team
configuration that may be shared across team members and checked into version
control. Other users who depend on this file are not affected by
uninstall/reinstall cycles.

Runtime state files removed on uninstall:
- `${CONFIG_ROOT}/governance.activation_intent.json` (activation intent)
- `${CONFIG_ROOT}/SESSION_STATE.json` (global active workspace pointer)
- `${WORKSPACES_HOME}/<fingerprint>/SESSION_STATE.json` (per-workspace state)
- `${WORKSPACES_HOME}/<fingerprint>/repo-identity-map.yaml`
- `${WORKSPACES_HOME}/<fingerprint>/repo-cache.yaml`
- `${WORKSPACES_HOME}/<fingerprint>/workspace-memory.yaml`
- `${WORKSPACES_HOME}/<fingerprint>/decision-pack.md`
- `${WORKSPACES_HOME}/<fingerprint>/business-rules.md`
- `${WORKSPACES_HOME}/<fingerprint>/plan-record.json`
- `${WORKSPACES_HOME}/<fingerprint>/plan-record-archive/` (archived plan records)
- `${WORKSPACES_HOME}/<fingerprint>/evidence/` (evidence directory)
- `${WORKSPACES_HOME}/<fingerprint>/.lock/` (workspace locks)
- `${WORKSPACES_HOME}/<fingerprint>/repo-map-digest.md`

Use `--keep-workspace-state` to preserve workspace state during uninstall (e.g., for reinstall without losing session history):

```bash
python install.py --uninstall --force --keep-workspace-state
```

Always preserved on uninstall (never deleted):
- opencode.json — user/team configuration (may be shared via version control)
- `governance.paths.json` (unless `--purge-paths-file` is explicitly passed)
- Non-governance user-owned files
