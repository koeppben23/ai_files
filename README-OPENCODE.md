## OpenCode Lifecycle

Back to bundle/install overview: `README.md`.

### Purpose

Launcher-first operator/model flow for starting and continuing governed OpenCode sessions.

### Lifecycle

1. Bootstrap workspace context:
   - macOS/Linux: `opencode-governance-bootstrap init --profile <solo|team|regulated> --repo-root <repo-root>`
   - Windows: `opencode-governance-bootstrap.cmd init --profile <solo|team|regulated> --repo-root <repo-root>`
   - optional alias (same semantics): `--set-operating-mode <solo|team|regulated>`
2. Open OpenCode Desktop in the same repository.
3. Run `/continue`.
4. If `/continue` lands at Phase 4, run `/ticket`, then `/plan`.
   Alternative path: run `/review` for read-only review feedback (no state change).
   `/ticket` is Plan Mode intake and persists Phase-4 ticket/plan evidence.
5. Use `/review` as the read-only rail entrypoint for quality review.
6. At Phase 6 Evidence Presentation Gate, run `/review-decision <approve|changes_requested|reject>`.
   Example: `/review-decision approve`.
7. `changes_requested` enters `Rework Clarification Gate`; clarify requested changes in chat, then run exactly one directed rail (`/ticket`, `/plan`, or `/continue`).
8. `reject` routes back to Phase 4 Ticket Input Gate; primary next action is `/ticket` with updated scope (alternative: `/review` for read-only feedback).
9. Use `/audit-readout` for a read-only audit snapshot.

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
