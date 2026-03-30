## OpenCode Lifecycle

Back to bundle/install overview: `README.md`.

### Purpose

Launcher-first operator/model flow for starting and continuing governed OpenCode sessions.
Runtime authority is `governance_runtime/`; legacy `governance/` is removed from productive surfaces.
Primary operator bootstrap path is `opencode-governance-bootstrap init ...`.
`python -m ...` invocation is internal/debug/compatibility-only and not the primary user path.

### Lifecycle

1. Bootstrap workspace context:
   - macOS/Linux: `opencode-governance-bootstrap init --profile <solo|team|regulated> --repo-root <repo-root>`
   - Windows: `opencode-governance-bootstrap.cmd init --profile <solo|team|regulated> --repo-root <repo-root>`
   - optional alias (same semantics): `--set-operating-mode <solo|team|regulated>`
2. Open OpenCode Desktop in the same repository.
3. Run `/continue`.
4. If `/continue` shows `Next action: run /hydrate.`, run `/hydrate` first.
5. After successful hydration, if Phase 4 is active, run `/ticket`, then `/plan`.
   Alternative path: run `/review` for read-only review feedback (no state change).
   `/ticket` is Plan Mode intake and persists Phase-4 ticket/plan evidence.
6. Use `/review` as the read-only rail entrypoint for quality review.
7. At Phase 6 Evidence Presentation Gate, run `/review-decision <approve|changes_requested|reject>`.
   Example: `/review-decision approve`.
8. `changes_requested` enters `Rework Clarification Gate`; clarify requested changes in chat, then run exactly one directed rail (`/ticket`, `/plan`, or `/continue`).
9. `reject` routes back to Phase 4 Ticket Input Gate; primary next action is `/ticket` with updated scope (alternative: `/review` for read-only feedback).
10. After `approve`, run `/implement` to start authorized implementation execution.
    - Direct mode (`pipeline_mode=false`, default): uses the active OpenCode Desktop LLM binding.
    - Pipeline mode (`pipeline_mode=true`): requires `AI_GOVERNANCE_EXECUTION_BINDING` and `AI_GOVERNANCE_REVIEW_BINDING`.
11. Use `/audit-readout` for a read-only audit snapshot.

Runtime persistence: `${WORKSPACE_HOME}/<repo_fingerprint>/...` with pointer `${SESSION_STATE_POINTER_FILE}`.
Path-binding: `${CONFIG_ROOT}/governance.paths.json`.

Install/layout truth:
- `${CONFIG_ROOT}` (`~/.config/opencode`) contains `commands/`, `plugins/`, `workspaces/`, `bin/`.
- `${LOCAL_ROOT}` (`~/.local/share/opencode`) contains `governance_runtime/`, `governance_content/`, `governance_spec/`, `VERSION`.
- Launcher: `${CONFIG_ROOT}/bin`.

## If execution is unavailable

If command execution is unavailable, ask the user to run the command locally and paste output.

## Minimal troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun installer with `--status`.
- `BLOCKED-VARIABLE-RESOLUTION`: validate binding resolution (`docs/install-layout.md`).
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure repo is a git checkout and `git` is in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE`: refresh evidence and rerun.

## Server/Client Configuration

Production LLM calls use OpenCode HTTP server API (https://opencode.ai/docs/server).

Configure in `~/.config/opencode/opencode.json`:
```json
{"server": {"hostname": "127.0.0.1", "port": 4096}}
```
OpenCode Desktop usually starts the server automatically.
If needed for diagnostics: `opencode serve --hostname 127.0.0.1 --port 4096`

`OPENCODE_PORT` controls how governance resolves the server URL. If Desktop is already
running on a non-default port, export `OPENCODE_PORT=<port>` before running `/hydrate`.

`OPENCODE_SESSION_ID` can be used for direct session-targeted API operations.
Hydration resolves the active session via `GET /session` and project path matching.

Optional auth:
```bash
export OPENCODE_SERVER_PASSWORD=your-password
export OPENCODE_SERVER_USERNAME=opencode  # optional, default
```

## Links

- Quickstart: `QUICKSTART.md`
- Bundle/install/uninstall: `README.md`
