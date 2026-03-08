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
1. normalize input
2. persist evidence
3. append audit event
4. reroute state

## Commands by platform

Chat text input:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --plan-persist --plan-text "<plan text>" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --plan-persist --plan-text "<plan text>" --quiet
```

File-based input:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --plan-persist --plan-file "/absolute/path/to/plan.md" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --plan-persist --plan-file "C:\absolute\path\to\plan.md" --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- Plan drafts in chat do not pass the Plan Record Preparation Gate by themselves; the persist command must run.
- After successful persist, run `/continue` to materialize gate advancement.
- This rail persists plan-record evidence; it does not perform implementation.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the persist command succeeded, confirm evidence was written and state was rerouted
- if a blocker or warning is present, render it with concise evidence and one recovery action

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language prompt is **not** a rail command. It does not trigger the plan persist command above, `/continue`, or any state write. Only the explicit `/plan` rail invocation is permitted to persist Phase-5 plan-record evidence. If the user sends free-text that implies plan submission, ask them to invoke `/plan` explicitly.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
