# Governance Implement

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/implement` persists the governance-to-implementation handoff after approved Phase 6 review.
The command is mutating - it writes implementation-start audit/state evidence.

`/implement` does not automatically execute code changes, start CI, or create PRs.

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
- Persists `implementation_started` handoff evidence and updates active gate/readout.
- Does not perform implementation work by itself.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the command succeeded, confirm implementation-start evidence was written
- if validation fails, render concise evidence and one recovery action

---

**Free-text guard:**
Free text like "go", "start implementing", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist implementation-start state. Only the explicit `/implement` rail invocation is permitted to write implementation-start evidence.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
