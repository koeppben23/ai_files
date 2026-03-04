# Governance Review

<!-- GOVERNANCE KERNEL BRIDGE — sole exception to rails-only constraint in this file -->
## Resume Session State

Preferred: load the current governance session state using the following read-only command, if local command execution is allowed in your environment:

```bash
{{PYTHON_COMMAND}} "{{SESSION_READER_PATH}}"
```

Use the YAML output as your governance context for the response below.

**If the command cannot be executed** (e.g., sandboxed environment, model policy, or tool error), ask the user to paste the output of the command above — or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

**If no snapshot is available**, proceed using only the context visible in the current conversation and state your assumptions explicitly before continuing.

---

`/review` is a Phase 4 review-only rail for PR or ticket review.
It is optimized for lead/staff review depth and does not perform implementation.

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
