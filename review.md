# Governance Review

<!-- rail-classification: READ-ONLY, GATE-EVALUATION, NO-STATE-CHANGE -->
## Resume Session State

The command below is a read-only session reader. It prints the current session state as YAML and does not modify any files.

Preferred (Tier A): load the current governance session state using the following read-only command:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader
```

Use the YAML output as your governance context for the response below. Do not infer or mutate any session state.

**Fallback (Tier B) — if the command cannot be executed** (e.g., sandboxed environment, model policy, or tool error), ask the user to paste the YAML output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

**Fallback (Tier C) — if no snapshot is available**, proceed using only the context visible in the current conversation and state your assumptions explicitly before continuing.

---

`/review` is a read-only rail entrypoint for PR or ticket review.
It surfaces during Phase 4 but the authoritative review gate is kernel- and phase-model-owned (see `phase_api.yaml` and `phases.md` Phase 5 Review Gate).
This rail is optimized for lead/staff review depth and does not perform implementation.
Phase 5 output class restrictions (forbidden: implementation, patch, diff, code_delivery) and plan self-review discipline are defined in `phase_api.yaml` `output_policy` on token `"5"` and explained in `master.md` Rule A and Rule B.

Review scope:
- architecture fit and contract integrity
- regression and operational risk
- test strategy quality and blind spots
- rollback, migration, and observability impact
- maintainability and long-term cost

Output contract:
- give a clear verdict: `approve` or `request changes`
- list findings with severity: `blocker`, `high`, `medium`, `low`
- include concise evidence and one concrete action per finding
- provide paste-ready PR comments (one per blocker/high + one summary)

Quality bar:
- prefer high-signal findings over stylistic noise
- focus on correctness, risk, and release safety first
- keep feedback actionable and specific to changed surfaces

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
