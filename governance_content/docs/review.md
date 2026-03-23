# Governance Review

<!-- rail-classification: READ-ONLY, GATE-EVALUATION, NO-STATE-CHANGE -->

## Purpose

`/review` is a read-only rail entrypoint for PR or ticket review.
The command below prints the current session state as guided governance output and does not modify any files.
It reads materialized review/session state and does not perform implementation changes.
It does not reroute phase state and does not replace `/review-decision`.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the rendered output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly before continuing.

## Interpretation scope

Use the rendered output as governance context for the response below. Do not infer or mutate any session state.

Read the current review gate from the materialized session output. Gate definitions and Phase 5 output class restrictions are in `phase_api.yaml`.

Review scope:
- architecture fit and contract integrity
- regression and operational risk
- test strategy quality and blind spots
- rollback, migration, and observability impact
- maintainability and long-term cost

## Response shape

- give a clear verdict aligned to final decision tokens: `approve` or `changes_requested`
- list findings with severity and one concrete action per finding
- provide paste-ready PR comments (one per blocker/high + one summary)

Quality bar:
- prefer high-signal findings over stylistic noise
- focus on correctness, risk, and release safety first
- keep feedback actionable and specific to changed surfaces

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
