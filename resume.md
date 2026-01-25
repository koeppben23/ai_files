RESUME — Controlled Session Continuation

Load and strictly enforce:
- master.md
- rules.md
- SCOPE-AND-CONTEXT.md

The SESSION_STATE provided by the user is the single authoritative source of truth.

Rules:
- Do NOT re-run discovery
- Do NOT change phases
- Do NOT reinterpret past decisions
- Do NOT introduce new assumptions
- Do NOT generate code unless explicitly allowed by the current gate state

Continue execution strictly according to:
SESSION_STATE.Phase
SESSION_STATE.Gates
SESSION_STATE.Next

If the SESSION_STATE is missing, incomplete, or inconsistent:
- Switch to BLOCKED mode
- Request the missing information
- Do NOT proceed

Acknowledge the loaded SESSION_STATE and wait for further instruction.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
