# Governance Review Decision

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/review-decision` persists the final Phase-6 review decision.
The command is mutating - it writes audit evidence and advances or reroutes state based on `decision`.
Free text alone does not write a final decision.

Accepted input contract:
- `decision=approve|changes_requested|reject` (required)
- `note=<text>` (optional)

Slash usage in chat:
- `/review-decision approve`
- `/review-decision changes_requested`
- `/review-decision reject`

No default is allowed. If `decision` is missing, do not persist and return a validation error.

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
- The reviewed evidence must be presented before final decision submission.
- `approve` moves to Workflow Complete, marks implementation as authorized, and sets the next explicit rail to `/implement`.
- `changes_requested` persists the decision and enters `Rework Clarification Gate`. Immediate change details are not required in the command.
- After `changes_requested`, start a guided clarification conversation in chat. No additional rail is required before this clarification.
- `reject` routes back to Phase 4 Ticket Input Gate and invalidates the current path.
- After `reject`, primary next action is `/ticket` with updated scope. Alternative: `/review` for read-only feedback before re-entering development.

Clarification prompt template after `changes_requested`:
- `Changes were requested. Please briefly describe what should be adjusted. I will then direct you to exactly one next rail.`

Directed rail selection after clarification:
- `/ticket` when scope/task/assignment changes
- `/plan` when scope stays but plan/approach changes
- `/continue` when only clarification is needed and no new intake/plan persistence is required

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the persist command succeeded, confirm the review decision evidence was written
- if the session state contains plan data, render a **Plan under review** section:
  - prefer `plan_under_review_summary` from the JSON payload (already normalized: max 6 lines, max 800 chars)
  - fallback to `review_package_plan_body` if summary is unavailable
  - truncate deterministically at line/char budget if content exceeds limits
- if validation fails, render the exact invalid decision and expected values
- **always** end with exactly one `Next action:` line as the final output line

---

**Free-text guard:**
Free text like "approve", "go", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist final review state. Only the explicit `/review-decision` rail invocation is permitted to write the final decision.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
