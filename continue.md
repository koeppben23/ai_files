# Governance Continue

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/continue` materializes and prints the current governance session state for this repository.
The command is mutating — it writes a materialization event.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader --materialize
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader --materialize
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the YAML output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly before continuing.

## Interpretation scope

Use the YAML output as governance context for the response below. Do not infer or mutate any session state beyond the materialized output.

## Response shape

- reflect current `SESSION_STATE.phase` and `SESSION_STATE.next`
- include delta-only progress for the active step
- if kernel reports a blocker or warning, render it with concise evidence and one recovery action

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language continuation prompt is **not** a rail command. It does not trigger the materialize command above or any state write. Only the explicit `/continue` rail invocation is permitted to materialize state. If the user sends free-text that implies continuation, respond conversationally without executing any governance commands.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
