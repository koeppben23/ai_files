# AGENTS (non-normative mirror)

AGENTS.md is a **non-normative mirror** for agent/front-end surfaces.
Normative precedence (SSOT): master.md > rules.md > active profiles > addons/templates.
If there is any conflict, **kernel wins** (master.md).

## Defaults
- Default to ARCHITECT (plan/decisions only) until explicit “Implement now”.
- No claim without evidence (recorded in SESSION_STATE), otherwise NOT_VERIFIED.
- Fail-closed: missing required inputs/addons/rulebooks => BLOCKED with recovery.
- When host capabilities permit, execute deterministic checks/commands directly and report evidence.
- After `/start`, complete bootstrap gates first; do not emit generic task-intake prompts before bootstrap state is established.

## Bootstrap
Bootstrap is governed exclusively by master.md Phase 0 gates.
This file does NOT constitute bootstrap evidence on its own.
- OpenCode binding evidence (preflight + path bindings) satisfies bootstrap.
- AGENTS.md presence alone does NOT satisfy bootstrap — it is a non-normative
  surface mirror only.

## Kernel contract (summary)
- Phases, gates, evidence, and the output envelope remain the kernel contract.
- AGENTS.md mirrors kernel sections but must not introduce new requirements.
- No host-binding tokens in this file.
