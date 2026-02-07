# Scorecard Calibration Shared Rulebook

This document defines shared scorecard calibration for cross-addon comparability.
It is designed as an advisory addon rulebook.

Precedence (binding): use the canonical order from `rules.md` Section 4.6.
As a shared advisory addon, this rulebook refines scorecard comparability and MUST NOT override master/core/profile constraints.

Activation (binding): manifest-owned via `profiles/addons/scorecardCalibration.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

Phase integration (binding):
- Phase 4: apply calibration defaults to planned scorecards.
- Phase 5: verify comparability/threshold contracts across active addons.
- Phase 6: block principal-grade declaration if calibration evidence is incomplete.

Evidence contract (binding):
- Maintain `SESSION_STATE.AddonsEvidence.scorecardCalibration.status` (`loaded|skipped|missing-rulebook`).
- Advisory warnings use `WARN-*` codes and recovery actions, not addon-only hard blocks.

---

## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)

### CAL-1 Standard criterion weights by tier (binding)

For principal scorecards in addon/template rulebooks, criteria weights MUST use this standard model:

- `TIER-LOW`: each active criterion weight = `2`
- `TIER-MEDIUM`: each active criterion weight = `3`
- `TIER-HIGH`: each active criterion weight = `5`

No custom weights are allowed unless explicitly documented as repo-specific exception with rationale and risk note.

### CAL-2 Critical-flag normalization (binding)

The following criteria classes MUST be marked `critical: true` when applicable:

- contract/integration correctness
- determinism and anti-flakiness
- rollback/recovery safety
- security semantics and authorization behavior

Non-critical criteria may exist, but cannot compensate for a failed critical criterion.

### CAL-3 Tier score thresholds (binding)

A principal-grade gate result may be `pass` only if all conditions are true:

- all applicable critical criteria are `pass`
- total score ratio meets threshold:
  - `TIER-LOW`: >= `0.80`
  - `TIER-MEDIUM`: >= `0.85`
  - `TIER-HIGH`: >= `0.90`

If threshold is missed, result MUST be `partial` or `fail` with recovery actions.

### CAL-4 Cross-addon comparability (binding)

When multiple addons are active in one ticket, scorecards MUST be directly comparable by using:

- canonical tier labels (`TIER-LOW|MEDIUM|HIGH`)
- standardized weight model from CAL-1
- identical pass thresholds from CAL-3

### CAL-5 Required SESSION_STATE calibration evidence (binding)

```yaml
SESSION_STATE:
  GateScorecards:
    principal_excellence:
      ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
      Score: 0
      MaxScore: 0
      ScoreRatio: 0.00
      Threshold: 0.80 | 0.85 | 0.90
      CalibrationVersion: v2.1.1
```

### CAL-6 Calibration warning code (binding)

If scorecard data is incomplete or non-comparable, emit `WARN-SCORECARD-CALIBRATION-INCOMPLETE`
and block principal-grade declaration (`not-verified`).

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
