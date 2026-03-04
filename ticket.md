# Governance Ticket

Use this command to persist Phase-4 intake evidence.

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
- `/continue` and `/review` are read-only rails.
- Ticket files or chat text do not change phase by themselves.
- Running the intake command writes evidence and reroutes from Phase 4 into the Phase 5 review gate path.
- Intake reroute is not implementation approval; code-producing output remains blocked until Phase 5 gates are approved.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
