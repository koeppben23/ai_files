# Principal Excellence Shared Rulebook

This document defines shared principal-grade review contracts.
It is designed as an advisory addon rulebook that can be reused across profiles.

Priority order on conflict:
`master.md` > `rules.md` (Core) > profile rulebook > this shared advisory rulebook.

---

## Principal Excellence Contract (Binding)

This contract is active only when this rulebook is loaded.

### Gate Review Scorecard (binding)

When active and touching changed scope, the workflow MUST maintain a scorecard entry with weighted criteria,
critical flags, and evidence references.

```yaml
SESSION_STATE:
  GateScorecards:
    principal_excellence:
      Score: 0
      MaxScore: 0
      Criteria:
        - id: PRINCIPAL-QUALITY-CLAIMS-EVIDENCED
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-001 | not-verified
        - id: PRINCIPAL-DETERMINISM-AND-TEST-RIGOR
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-002 | not-verified
        - id: PRINCIPAL-ROLLBACK-OR-RECOVERY-READY
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-003 | not-verified
```

### Claim-to-evidence (binding)

Any non-trivial claim (for example: contract-safe, tests green, architecture clean, deterministic)
MUST map to an `evidenceRef`.
If evidence is missing, the claim MUST be marked `not-verified`.

### Exit criteria (binding)

- All criteria with `critical: true` MUST be `pass` before declaring principal-grade completion.
- Advisory addons remain non-blocking but MUST emit WARN + recovery when critical criteria are not pass.
- Required addons/templates may block code-phase according to master/core/profile policy.

### Recovery when evidence is missing (binding)

Emit a warning code plus concrete recovery commands/steps and keep completion status as `not-verified`.
Recommended code: `WARN-PRINCIPAL-EVIDENCE-MISSING`.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
