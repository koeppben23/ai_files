# Governance Hydrate

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/hydrate` is the first session-bound governance step after OpenCode Desktop starts.
It binds the governance runtime to the active OpenCode session, validates the knowledge base,
and prepares the session for productive work.

The command is mutating — it writes hydration evidence and reroutes kernel state.

**Preconditions:**
1. OpenCode Desktop must be running
2. Server must be reachable on the configured port (default: 4096)
3. At least one session must exist

**Hydration flow:**
1. Check server reachability via GET /global/health
2. Resolve active session via GET /session
3. Validate knowledge base (Repo Map, Workspace Memory, Decision Pack, Business Rules)
4. Build hydration brief
5. Write brief to session via POST /session/:id/message
6. Persist hydration receipt
7. Open ticket gate

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --hydrate --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --hydrate --quiet
```

## If execution is unavailable

If the command cannot be executed, verify:
1. OpenCode Desktop is running
2. Server is reachable: `curl http://127.0.0.1:4096/global/health`
3. OPENCODE_PORT matches the server port (default: 4096)

If OpenCode Desktop is not running, start it with:
```bash
opencode serve --port 4096 --hostname 127.0.0.1
```

Or set OPENCODE_PORT before starting OpenCode Desktop:
```bash
export OPENCODE_PORT=4096
opencode
```

If OpenCode Desktop is already running on another port, set `OPENCODE_PORT` to that port before running `/hydrate`.

## Interpretation scope

- `/hydrate` must run before `/ticket` or `/review`
- Without successful hydration, `/ticket` and `/continue` are blocked
- Hydration is idempotent — running it multiple times refreshes the session binding
- The hydration brief contains: architecture, modules, entry points, invariants, decisions, rules

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition`
- if hydration succeeded, include `hydrated_session_id` and `hydrated_at`
- confirm evidence was written and ticket gate is open
- if a blocker or warning is present, render it with concise evidence and one recovery action

**After successful hydration:**
- Next action: run `/ticket`.

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", or any other natural-language prompt is **not** a rail command. It does not trigger the hydrate command. Only the explicit `/hydrate` rail invocation is permitted to bind the session. If the user sends free-text that implies hydration, ask them to invoke `/hydrate` explicitly.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
