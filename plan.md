# Governance Plan

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/plan` persists Phase-5 plan-record evidence.
The command is mutating — it writes evidence and reroutes kernel state.
Chat text or a file path alone does not change gate state; the persist command below must be executed to write evidence and reroute state.

Two accepted inputs:
- plan text in chat
- a local file path containing plan text

Deterministic persist flow:
1. read input
2. canonicalize text
3. append plan-record version evidence in active workspace
4. append plan persist audit event
5. reroute kernel state

## Commands by platform

Chat text input:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --entrypoint governance.entrypoints.phase5_plan_record_persist --plan-text "<plan text>" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --entrypoint governance.entrypoints.phase5_plan_record_persist --plan-text "<plan text>" --quiet
```

File-based input:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --entrypoint governance.entrypoints.phase5_plan_record_persist --plan-file "/absolute/path/to/plan.md" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --entrypoint governance.entrypoints.phase5_plan_record_persist --plan-file "C:\absolute\path\to\plan.md" --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- `/continue` is the state materialization rail.
- Plan drafts in chat do not pass the Plan Record Preparation Gate by themselves.
- Run this persist command first when `active_gate` is `Plan Record Preparation Gate` and `plan_record_status` is absent.
- After successful persist, run `/continue` to materialize gate advancement.

## Response shape

- report current `phase` and `next` after plan persist
- report `active_gate` and `next_gate_condition`
- if the persist command succeeded, confirm evidence was written and state was rerouted
- if a blocker or warning is present, render it with concise evidence and one recovery action

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language prompt is **not** a rail command. It does not trigger the plan persist command above, `/continue`, or any state write. Only the explicit `/plan` rail invocation is permitted to persist Phase-5 plan-record evidence. If the user sends free-text that implies plan submission, ask them to invoke `/plan` explicitly.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
