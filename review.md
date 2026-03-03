# Governance Review

<!-- GOVERNANCE KERNEL BRIDGE — sole exception to rails-only constraint in this file -->
## MANDATORY FIRST STEP

Before responding, execute the following command to load the current governance session state:

```bash
{{PYTHON_COMMAND}} "{{SESSION_READER_PATH}}"
```

Use the YAML output as your governance context for the response below.
If the command fails, report the error verbatim and stop.

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
