# Governance Review

<!-- rail-classification: READ-ONLY, GATE-EVALUATION, NO-STATE-CHANGE -->

## Purpose

`/review` is a read-only rail entrypoint for PR or ticket review.
The command below prints the current session state as YAML and does not modify any files.
It reads materialized review/session state and does not perform implementation changes.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader
```

## If execution is unavailable

If the command cannot be executed (e.g., sandboxed environment, model policy, or tool error), ask the user to paste the YAML output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly before continuing.

## Interpretation scope

Use the YAML output as governance context for the response below. Do not infer or mutate any session state.

The review gate state is defined by the materialized session output. It surfaces during Phase 4 but the review gate is phase-model-owned (see `phase_api.yaml` and `phases.md` Phase 5 Review Gate).
This rail is optimized for lead/staff review depth and does not perform implementation.
Phase 5 output class restrictions (forbidden: implementation, patch, diff, code_delivery) and plan self-review discipline are defined in `phase_api.yaml` `output_policy` on token `"5"` and explained in `master.md` Rule A and Rule B.

Review scope:
- architecture fit and contract integrity
- regression and operational risk
- test strategy quality and blind spots
- rollback, migration, and observability impact
- maintainability and long-term cost

## Response shape

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
