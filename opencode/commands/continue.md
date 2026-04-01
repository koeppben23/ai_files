---
description: Materialize and print the current governance session state for this repository.
---

# Governance Continue

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Context

This command is part of a **locally installed governance extension** for OpenCode.
It is not a native OpenCode core feature.  The governance runtime, its command
rails, and all referenced files reside in the local OpenCode configuration
directory as part of the project's governance setup.

## Purpose

`/continue` materializes and prints the current governance session state for this repository.
The command is mutating — it writes a materialization event.
In normal mode the output is a guided user-facing readout, not a YAML field dump.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader --materialize
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader --materialize
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the rendered output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly before continuing.

## Interpretation scope

Use the rendered output as governance context for the response below. Do not infer or mutate any session state beyond the materialized output.

For Phase 5.4 (Business Rules Validation): if extraction evidence shows all missing surfaces were filtered as non-business (`filtered_non_business`) and no invalid-rule/source/render/segmentation defects are present, treat the gate as `not-applicable` rather than `gap-detected`.

## Response shape

- reflect current `SESSION_STATE.phase` and `SESSION_STATE.next`; include delta-only progress for the active step
- if session contains plan data, render **Plan under review** section (prefer `plan_under_review_summary` normalized to max 6 lines/800 chars; fallback to `review_package_plan_body`)
- if kernel reports blocker/warning, render with evidence and one recovery action
- **always** end with exactly one `Next action:` line as final output; for Phase 4 / Ticket Input Gate include both: `/ticket` and `/review`

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language continuation prompt is **not** a rail command. It does not trigger the materialize command above or any state write. Only the explicit `/continue` rail invocation is permitted to materialize state. If the user sends free-text that implies continuation, respond conversationally without executing any governance commands.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
