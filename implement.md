# Governance Implement

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/implement` starts execution of the approved implementation plan after approved Phase 6 governance review.
The command is mutating. It orchestrates an external code executor and writes governance diagnostics/state.

`/implement` follows a controller/executor split:
- load approved plan, hotspots, constraints, and required checks
- write executor input context (`.governance/implementation/llm_edit_context.json`)
- invoke configured external LLM executor (the only actor allowed to change domain files)
- run internal implementation self-review (validation-only; no local domain edits)
- collect git diff evidence and validate plan-coverage plus targeted checks
- persist validation/audit evidence and fail closed when requirements are not met

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --implement-start --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --implement-start --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- Valid only after final review decision `approve` (Workflow Complete).
- `/implement` is a controller + validator; it must not locally edit domain/source files.
- Local writes are restricted to governance diagnostics/state (for example `.governance/implementation/*`, session state, and audit events).
- Domain/source edits must come exclusively from the configured external executor.
- Ends in `Implementation Review Complete` (ready to continue) or `Implementation Blocked`.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the command succeeded, confirm implementation execution evidence was written
- if validation fails, render concise evidence and one recovery action

---

**Free-text guard:**
Free text like "go", "start implementing", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist implementation execution state. Only the explicit `/implement` rail invocation is permitted to write implementation execution evidence.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
