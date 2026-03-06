# Governance Ticket

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

Use this command to persist Phase-4 intake evidence.
Chat text or a file path alone does not change phase or pass any gate; the intake command below must be executed to write evidence and reroute state.

Two accepted inputs:
- ticket/task text in chat
- a local file path containing ticket/task text

Deterministic intake flow:
1. read input
2. canonicalize text
3. persist `Ticket`/`Task` and matching digest(s) in active `SESSION_STATE`
4. append intake audit event
5. reroute kernel state

Recommended local command (chat text input):

```bash
{{PYTHON_COMMAND}} -m governance.entrypoints.phase4_intake_persist --ticket-text "<ticket text>" --quiet
```

File-based input:

```bash
{{PYTHON_COMMAND}} -m governance.entrypoints.phase4_intake_persist --ticket-file "/absolute/path/to/ticket.md" --quiet
```

Notes:
- `/review` is read-only; `/continue` is the kernel-owned state materialization rail.
- Ticket files or chat text do not change phase by themselves.
- Running the intake command writes evidence and reroutes from Phase 4 into the Phase 5 review gate path.
- Intake reroute is not implementation approval; code-producing output remains blocked until Phase 5 gates are approved and session transitions to Phase 6.

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language prompt is **not** a rail command. It must NEVER trigger the intake command above, `/continue`, or any authoritative state write. Only the explicit `/ticket` rail invocation is permitted to persist Phase-4 intake evidence. If the user sends free-text that implies ticket submission, ask them to invoke `/ticket` explicitly.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
