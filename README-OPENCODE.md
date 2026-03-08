## OpenCode Lifecycle

Back to bundle/install overview: `README.md`.

### Purpose

Launcher-first operator/model flow for starting and continuing governed OpenCode sessions.

### Lifecycle

1. Bootstrap workspace context:
   - macOS/Linux: `opencode-governance-bootstrap --repo-root <repo-root>`
   - Windows: `opencode-governance-bootstrap.cmd --repo-root <repo-root>`
2. Open OpenCode Desktop in the same repository.
3. Run `/continue`.
4. If `/continue` lands at Phase 4, run `/ticket`, then `/plan`.
   This is Plan Mode intake and persists Phase-4 ticket/plan evidence.
5. Use `/review` as the read-only rail entrypoint for quality review.
6. Use `/audit-readout` for a read-only audit snapshot.

Runtime persistence is repo-scoped under `${WORKSPACES_HOME}/<repo_fingerprint>/...` with global pointer `${SESSION_STATE_POINTER_FILE}`.
Path-binding bootstrap depends on `${CONFIG_ROOT}/commands/governance.paths.json`.

## If execution is unavailable

If command execution is unavailable, ask the user to run the command locally and paste the output.

## Minimal troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun installer and verify with `--status`.
- `BLOCKED-VARIABLE-RESOLUTION`: validate binding resolution (`docs/install-layout.md`).
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure repo is a git checkout and `git` is in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE`: refresh evidence and rerun.

## Links

- Quickstart flow: `QUICKSTART.md`
- Bundle/install/uninstall surface: `README.md`
