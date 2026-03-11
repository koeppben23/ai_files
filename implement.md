# Governance Implement

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/implement` starts execution of the approved implementation plan after approved Phase 6 governance review.
The command is mutating - it writes execution, internal review-loop, and implementation-package evidence.

`/implement` runs a deterministic implementation loop:
- load approved plan
- start repository changes
- run internal implementation self-review
- apply targeted revisions when needed
- verify and either present implementation package or fail closed with blockers

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
- Starts implementation execution and internal review/revision/verification loop.
- Ends in `Implementation Presentation Gate` (decision-ready) or `Implementation Blocked`.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the command succeeded, confirm implementation execution evidence was written
- if validation fails, render concise evidence and one recovery action

---

**Free-text guard:**
Free text like "go", "start implementing", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist implementation execution state. Only the explicit `/implement` rail invocation is permitted to write implementation execution evidence.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
