# Governance Implementation Decision

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/implementation-decision` persists the final external decision for implemented results.
The command is mutating - it writes audit evidence and routes implementation state.

Accepted input contract:
- `decision=approve|changes_requested|reject` (required)
- `note=<text>` (optional)

Slash usage in chat:
- `/implementation-decision approve`
- `/implementation-decision changes_requested`
- `/implementation-decision reject`

No default is allowed. If `decision` is missing, do not persist and return a validation error.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --implementation-decision-persist --decision "approve" --note "Implementation looks good" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --implementation-decision-persist --decision "approve" --note "Implementation looks good" --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- Valid only at `Implementation Presentation Gate`.
- `approve` means implemented result accepted.
- `changes_requested` enters `Implementation Rework Clarification Gate`.
- `reject` enters `Implementation Blocked`.
- `approve` is blocked fail-closed when critical findings or hard blockers remain.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if persist succeeded, confirm implementation-decision evidence was written
- if validation fails, render the invalid decision and expected values

---

**Free-text guard:**
Free text like "approve", "go", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist implementation decision state. Only the explicit `/implementation-decision` rail invocation is permitted to write final implementation decision evidence.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
