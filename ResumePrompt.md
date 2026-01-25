RESUME-PROMPT — Controlled Session Recovery

INSTRUCTION (highest priority):
This is a controlled resume of an existing engineering session.
Load and strictly enforce the provided governance and rule documents.
The SESSION_STATE below is the single authoritative source of truth and overrides any implicit assumptions.

1. Governance & Rules (load in this order):
- master.md             (workflow, phases, gates)
- rules.md              (technical & quality rules)
- SCOPE-AND-CONTEXT.md  (governance, responsibility boundaries)

2. Restored SESSION_STATE (authoritative, do not reinterpret):

<<< PASTE LAST [SESSION_STATE] BLOCK HERE — UNCHANGED >>>

3. Execution Directive:

- Confirm receipt of the SESSION_STATE.
- Confirm current Phase, Confidence Level, and Gate Status.
- Continue work **directly in Phase <X>** as specified in NEXT STEP.
- Perform **only fact validation and consistency checks** required for this phase.
- Do NOT generate code, diffs, or new artifacts unless the gate status explicitly allows it.
- If required facts are missing or inconsistent:
  - Switch to BLOCKED or DEGRADED mode as defined in rules.md.
  - Report blockers explicitly.
  - Do NOT infer or reconstruct missing information.

4. Output Constraints:

- Be concise and deterministic.
- No re-discovery of repository or APIs.
- No re-planning unless explicitly requested.
- No repetition of rules or governance text.
- No creative extrapolation.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF RESUME-PROMPT
