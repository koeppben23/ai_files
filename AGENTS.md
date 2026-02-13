This repo uses Governance Kernel rules

Default to ARCHITECT plan-only until explicit ‘Implement now’
No claim without evidence
If evidence missing → respond BLOCKED + recovery
Do not assume ability to run commands; request evidence

AGENTS.md is a non-normative mirror of the Kernel; conflicts resolve to master.md

Bootstrap Evidence: OpenCodeBinding (governance.paths.json + preflight) OR AGENTS.md Presence (Codex surface)

Bootstrap is satisfied by either of the two equivalent surfaces.

OpenCode /start is the canonical entrypoint for OpenCode workflows.

- Phases, Gates, Fail-closed, Evidence, Output envelope remain the Kernel contract.
- AGENTS.md mirrors kernel sections but without host-binding tokens.

Kernel wins on conflict. AGENTS.md is only an alternative frontend surface.

Note: AGENTS.md must not contain host-binding tokens (no `${COMMANDS_HOME}`, no `governance.paths.json`).
