Continue the current session strictly according to the canonical SESSION_STATE (see `SESSION_STATE_SCHEMA.md`).

- Do NOT re-run discovery
- Do NOT change phases
- Do NOT bypass gates
- Execute ONLY the step defined in SESSION_STATE.Next

Profile rule:
- Do NOT change SESSION_STATE.ActiveProfile. If it is missing/ambiguous, stop and request it.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
