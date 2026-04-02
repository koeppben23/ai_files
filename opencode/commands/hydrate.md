---
description: Bind governance runtime to the active OpenCode session — validates knowledge base and prepares for productive work.
---

# Governance Hydrate

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Context

This command is part of a **locally installed governance extension** for OpenCode.
It is not a native OpenCode core feature.  The governance runtime, its command
rails, and all referenced files reside in the local OpenCode configuration
directory as part of the project's governance setup.
The context files `master.md` and `rules.md` loaded via `instructions` in
`opencode.json` describe the governance system's authority, constraints, and
developer mandates.

## Purpose

`/hydrate` is the first session-bound governance step after OpenCode Desktop starts.
It binds the governance runtime to the active OpenCode session, validates the knowledge base,
and prepares the session for productive work.

The command is mutating — it writes hydration evidence and reroutes kernel state.

**Preconditions:**
1. OpenCode Desktop must be running
2. The governance runtime must be able to reach the OpenCode server (see *Server Discovery* below)
3. At least one session must exist

**Hydration flow:**
1. Discover the running OpenCode server (see *Server Discovery*)
2. Check server reachability via `GET /global/health`
3. Resolve active session via `GET /session`
4. Validate knowledge base (Repo Map, Workspace Memory, Decision Pack, Business Rules)
5. Build hydration brief
6. Write brief to session via `POST /session/:id/message`
7. Persist hydration receipt
8. Open ticket gate

## Server Discovery

The governance runtime supports two server modes, resolved as:
**CLI `--server-mode` > ENV `OPENCODE_SERVER_MODE` > default `attach_existing`**.

### `attach_existing` (default)

The runtime discovers a running OpenCode server on the local machine
automatically.  It uses OS-level process inspection to find a listening
OpenCode process, then confirms reachability via `GET /global/health`.

- **No port configuration required** — the runtime finds the server regardless
  of which port OpenCode Desktop chose.
- If no running server is found, hydration is **blocked** (it never starts one).
- If multiple candidates are found, hydration is **blocked** (ambiguous).

### `managed` (explicit override)

Set `--server-mode managed` or `OPENCODE_SERVER_MODE=managed` to have the
governance runtime manage its own server lifecycle on a fixed port.  In this
mode, the runtime may start the server if absent.  This requires explicit
port configuration via `opencode.json` `server.port` or the `OPENCODE_PORT`
environment variable.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --hydrate --quiet --project-path "{{PROJECT_PATH}}"
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --hydrate --quiet --project-path "{{PROJECT_PATH}}"
```

## If execution is unavailable

If the command cannot be executed, verify:
1. OpenCode Desktop is running (the `attach_existing` default mode requires it)
2. The server is reachable — the governance runtime will report the discovered
   URL and health status in its output
3. If using `managed` mode, ensure port configuration is correct

If OpenCode Desktop is not running:
- **Preferred:** Start OpenCode Desktop normally and rerun `/hydrate`.
- **Managed mode only:** Set `OPENCODE_SERVER_MODE=managed` and configure a
  fixed port before running `/hydrate`.

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
- Next action: run `/ticket` or `/review`.

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", or any other natural-language prompt is **not** a rail command. It does not trigger the hydrate command. Only the explicit `/hydrate` rail invocation is permitted to bind the session. If the user sends free-text that implies hydration, ask them to invoke `/hydrate` explicitly.

Copyright 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
