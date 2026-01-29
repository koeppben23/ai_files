Continue the current session strictly according to the canonical SESSION_STATE (see `SESSION_STATE_SCHEMA.md`).

- Do NOT re-run discovery

Execute ONLY the step referenced by `SESSION_STATE.Next`.

Binding preflight:
1) If `SESSION_STATE.Phase` is at least Phase 2 AND BOTH `SESSION_STATE.RepoMapDigest` and `SESSION_STATE.RepoModel` are missing:
   - set `Mode=BLOCKED`
   - set `Next="BLOCKED-Phase2-RepoDiscovery"`
   - record blocker `REPO-DIGEST-MISSING`
   - request minimal action: rerun Phase 2 (repo discovery) in the current repo scope
2) If `SESSION_STATE.Phase` is at least Phase 2 AND `SESSION_STATE.WorkingSet` is missing:
   - set `Mode=DEGRADED`
   - record warning `WORKING-SET-MISSING`
   - continue, but require `WorkingSet` to be populated in the next Phase 4 output
3) If `SESSION_STATE.Phase` is at least Phase 4 AND `SESSION_STATE.TouchedSurface` is missing:
   - set `Mode=DEGRADED`
   - record warning `TOUCHED-SURFACE-MISSING`
   - continue, but require `TouchedSurface` to be populated in the next Phase 4 output
4) If `SESSION_STATE.FastPath=true`:
   - in Phase 5, apply reduced review scope as defined in `master.md`

Profile rule:
- Do NOT change `SESSION_STATE.ActiveProfile`. If it is missing/ambiguous, stop and request it.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
