# SESSION_STATE_SCHEMA

## Required Keys (Phase 1.1+)

SESSION_STATE MUST include:

- Phase
- Mode
- Next
- ConfidenceLevel
- Gates
- LoadedRulebooks:
    core: string | ""
    profile: string | ""
- ActiveProfile: string | ""
- ProfileSource: user-explicit | auto-detected-single | repo-fallback | deferred
- ProfileEvidence: string

### Lazy Loading Invariants (BINDING)

- Until Phase 2 completes:
  - ActiveProfile MAY be ""
  - ProfileSource MUST be "deferred"

- Until Phase 4 begins:
  - LoadedRulebooks.core MAY be ""

- If Phase >= 4 AND LoadedRulebooks.core == "":
  → BLOCKED

This schema is authoritative.