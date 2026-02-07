# Principal Excellence Shared Rulebook

This document defines shared principal-grade review contracts.
It is designed as an advisory addon rulebook that can be reused across profiles.

Precedence (binding): use the canonical order from `rules.md` Section 4.6.
As a shared advisory addon, this rulebook refines review behavior and MUST NOT override master/core/profile constraints.

Activation (binding): manifest-owned via `profiles/addons/principalExcellence.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

Phase integration (binding):
- Phase 4: initialize scorecard criteria for touched scope.
- Phase 5: evaluate criteria with evidence refs.
- Phase 6: verify unresolved critical failures remain `not-verified` with recovery steps.

Evidence contract (binding):
- Maintain `SESSION_STATE.AddonsEvidence.principalExcellence.status` (`loaded|skipped|missing-rulebook`).
- Advisory findings are represented via WARN codes in `warnings[]`; do not hard-block solely from this addon.

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

## Examples (GOOD/BAD)

GOOD:
- Claim "tests green" is linked to `evidenceRef: EV-023` with command and pass summary in BuildEvidence.

BAD:
- Claim "architecture is clean" appears in narrative text without any evidence mapping.

## Troubleshooting

1) Symptom: Critical criterion fails with `not-verified`
- Cause: missing or stale evidenceRef
- Fix: attach fresh command/output evidence and rerun scorecard evaluation.

2) Symptom: Advisory addon emits repeated WARNs across phases
- Cause: recovery action is documented but not executed
- Fix: execute listed recovery commands and update scorecard results/evidence refs.

3) Symptom: Principal-grade declaration blocked at final QA
- Cause: one or more `critical: true` criteria not `pass`
- Fix: resolve failed criterion and re-evaluate before declaring completion.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
