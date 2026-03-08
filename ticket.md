# Governance Ticket

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/ticket` persists Phase-4 intake evidence.
The command is mutating — it writes evidence and reroutes kernel state.
Chat text or a file path alone does not change phase or pass any gate; the intake command below must be executed to write evidence and reroute state.

Two accepted inputs:
- ticket/task text in chat
- a local file path containing ticket/task text

Deterministic intake flow:
1. normalize input
2. persist evidence
3. append audit event
4. reroute state

## Commands by platform

Chat text input:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --entrypoint governance.entrypoints.phase4_intake_persist --ticket-text "<ticket text>" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --entrypoint governance.entrypoints.phase4_intake_persist --ticket-text "<ticket text>" --quiet
```

File-based input:

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --entrypoint governance.entrypoints.phase4_intake_persist --ticket-file "/absolute/path/to/ticket.md" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --entrypoint governance.entrypoints.phase4_intake_persist --ticket-file "C:\absolute\path\to\ticket.md" --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- Ticket files or chat text do not change phase by themselves; the intake command must run.
- Intake reroute writes evidence and advances from Phase 4 into the Phase 5 review gate path.
- Intake reroute is not implementation approval; code-producing output remains blocked until Phase 6.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after intake
- if the intake command succeeded, confirm evidence was written and state was rerouted
- if a blocker or warning is present, render it with concise evidence and one recovery action

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language prompt is **not** a rail command. It does not trigger the intake command above, `/continue`, or any state write. Only the explicit `/ticket` rail invocation is permitted to persist Phase-4 intake evidence. If the user sends free-text that implies ticket submission, ask them to invoke `/ticket` explicitly.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
