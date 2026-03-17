# Scorecard Calibration Shared Rulebook

This document defines shared scorecard calibration for cross-addon comparability.
It is designed as an advisory addon rulebook.

## Intent (binding)

Keep multi-addon scorecards comparable by enforcing common weights, thresholds, and calibration evidence.

## Scope (binding)

Scorecard weighting/threshold normalization, critical-criterion behavior, and comparability evidence requirements.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
As a shared advisory addon, this rulebook refines scorecard comparability and MUST NOT override master/core/profile constraints.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/scorecardCalibration.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 4: apply calibration defaults to planned scorecards.
- Phase 5: verify comparability/threshold contracts across active addons.
- Phase 6: block principal-grade declaration if calibration evidence is incomplete.

## Evidence contract (binding)

- Maintain `SESSION_STATE.AddonsEvidence.scorecardCalibration.status` (`loaded|skipped|missing-rulebook`).
- Advisory warnings use `WARN-*` codes and recovery actions, not addon-only hard blocks.

## Tooling (recommended)

- Use gate scorecard outputs and repo-native checks to populate calibration fields consistently.
- If calibration data is incomplete, emit WARN and keep principal-grade claims `not-verified`.

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

## Examples (GOOD/BAD)

GOOD:
- Two active addons both use `TIER-MEDIUM` with weight `3` per active criterion and threshold `0.85`, enabling direct comparison.

BAD:
- One addon uses custom weight `7` without documented exception, making scorecards non-comparable.

## Troubleshooting

1) Symptom: Scorecards cannot be compared across addons
- Cause: non-canonical weights/thresholds or missing `ActiveTier`
- Fix: reapply CAL-1/CAL-3 defaults and include calibration fields in SESSION_STATE.

2) Symptom: Gate marked pass despite failed critical criterion
- Cause: non-critical points incorrectly compensated the critical failure
- Fix: enforce CAL-2 and downgrade result to `partial` or `fail` with recovery.

3) Symptom: Principal-grade declaration blocked with calibration warning
- Cause: incomplete scorecard metadata (`ScoreRatio`, `Threshold`, or `CalibrationVersion` missing)
- Fix: populate required CAL-5 fields and rerun gate evaluation.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
