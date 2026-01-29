Continue the current session strictly according to the canonical SESSION_STATE (see `SESSION_STATE_SCHEMA.md`).

- Do NOT re-run discovery
- Do NOT change phases
- Do NOT bypass gates

Execute ONLY the step referenced by SESSION_STATE.Next.

Binding preflight:
1) If SESSION_STATE.Phase >= 2 AND SESSION_STATE.RepoModel is missing:
   - set Mode=BLOCKED
   - set Next="Phase2-RepoDiscovery"
   - request minimal action: rerun Phase 2 (repo discovery)
2) If SESSION_STATE.Phase >= 4 AND SESSION_STATE.TouchedSurface is missing:
   - set Mode=DEGRADED
   - record warning "TOUCHED-SURFACE-MISSING"
   - continue, but require TouchedSurface to be populated in the next Phase 4 output
3) If SESSION_STATE.FastPath=true:
   - In Phase 5, apply reduced review scope as defined in master.md

Profile rule:
- Do NOT change SESSION_STATE.ActiveProfile. If it is missing/ambiguous, stop and request it.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
