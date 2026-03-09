# Governance Review Decision

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/review-decision` persists the final Phase-6 review decision.
The command is mutating - it writes audit evidence and advances or reroutes state based on `decision`.
Free text alone does not write a final decision.

Accepted input contract:
- `decision=approve|changes_requested|reject` (required)
- `note=<text>` (optional)

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --review-decision-persist --decision "approve" --note "Looks good" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --review-decision-persist --decision "approve" --note "Looks good" --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- Valid only at Phase 6 Evidence Presentation Gate.
- `approve` moves to Workflow Complete.
- `changes_requested` resets the Phase 6 implementation review loop.
- `reject` routes back to Phase 4 Ticket Input Gate.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the persist command succeeded, confirm the review decision evidence was written
- if validation fails, render the exact invalid decision and expected values

---

**Free-text guard:**
Free text like "approve", "go", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist final review state. Only the explicit `/review-decision` rail invocation is permitted to write the final decision.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
