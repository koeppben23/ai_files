RESUME-PROMPT — Controlled Session Recovery (Guidance Template)

INSTRUCTION (template guidance):
This is a controlled resume of an existing engineering session.
Use the provided governance and rule documents as context.
Kernel/config remain authoritative for runtime decisions.

1. Governance & Rules (recommended context order):
- master.md             (workflow, phases, gates)
- rules.md              (technical & quality rules)
- SCOPE-AND-CONTEXT.md  (governance, responsibility boundaries)
- the active profile rulebook referenced by SESSION_STATE.ActiveProfile (e.g., rules.backend-java.md)

2. Restored SESSION_STATE (continuity context):

Profile guidance:
- If `SESSION_STATE.ActiveProfile` is missing or ambiguous, ask for clarification and avoid default assumptions.

<<< PASTE LAST [SESSION_STATE] BLOCK HERE — UNCHANGED >>>

3. Execution Guidance:

- Confirm receipt of the SESSION_STATE.
- Confirm current Phase, Confidence Level, and Gate Status.
- Continue work in the phase implied by `SESSION_STATE.Next` and current gate context.
- Prioritize fact validation and consistency checks for the current step.
- Avoid generating code/diffs unless requested and gate posture allows it.
- If required facts are missing or inconsistent:
  - report blockers explicitly,
  - request minimal missing information,
  - avoid reconstructing unknown facts.

4. Output Constraints:

- Be concise and deterministic.
- No re-discovery of repository or APIs.
- No re-planning unless explicitly requested.
- No repetition of rules or governance text.
- No creative extrapolation.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF RESUME-PROMPT
