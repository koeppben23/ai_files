# Fallback Minimum Profile

Purpose:
Provide a mandatory baseline when a target repository lacks explicit
standards (no CI, no test conventions, no documented build steps).

## Activation condition
This profile applies ONLY when no repo-local standards are discoverable.

## Mandatory baseline (MUST)
- Identify how to build and verify the project.
  If not present, propose and establish a minimal runnable baseline.
- Do not claim verification without executed checks or explicit justification.
- For non-trivial changes, introduce or recommend minimal automation (CI).

## Minimum verification (MUST)
At least one of:
- Unit tests for core logic changes
- Integration test for boundary changes when feasible
- Smoke verification (build + basic run) if tests are absent

## Documentation (MUST)
- Ensure build/test instructions exist (create minimal documentation if missing).
- Record non-trivial decisions in ADR.md or an equivalent mechanism.

## Quality heuristics (SHOULD)
- Deterministic behavior; no hidden mutable state.
- Coherent error handling; no silent failures.
- Logging at critical boundaries without leaking sensitive data.

## Portability (MUST when persisting)
Use platform-neutral storage locations as defined in rules.md.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# End of file — rules.fallback-minimum.md

---

## Principal Excellence Contract (Binding)

This rulebook is considered principal-grade only when the contract below is satisfied.

### Gate Review Scorecard (binding)

When this rulebook is active and touches changed scope, the workflow MUST maintain a scorecard entry with weighted criteria, critical flags, and evidence references.

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

Any non-trivial claim (for example: contract-safe, tests green, architecture clean, deterministic) MUST map to an `evidenceRef`.
If evidence is missing, the claim MUST be marked `not-verified`.

### Exit criteria (binding)

- All criteria with `critical: true` MUST be `pass` before declaring principal-grade completion.
- Advisory add-ons MUST remain non-blocking, but MUST emit WARN status code + recovery when critical criteria are not pass.
- Required templates/add-ons MAY block code-phase according to master/core/profile policy when critical criteria cannot be satisfied safely.

### Recovery when evidence is missing (binding)

Emit a warning code plus concrete recovery commands/steps and keep completion status as `not-verified`.
Recommended code: `WARN-PRINCIPAL-EVIDENCE-MISSING`.

---

## Principal Hardening v2 - Fallback Minimum Safety (Binding)

### FMPH2-1 Baseline scorecard criteria (binding)

When fallback profile is active, the scorecard MUST evaluate and evidence:

- `FALLBACK-BUILD-VERIFY-EXECUTED`
- `FALLBACK-MINIMUM-TEST-COVERAGE`
- `FALLBACK-DOCS-UPDATED`
- `FALLBACK-RISK-NOTED`
- `FALLBACK-ROLLBACK-OR-RECOVERY-PLAN`

Each criterion MUST include an `evidenceRef`.

### FMPH2-2 Minimum acceptance matrix (binding)

Fallback completion requires evidence for at least one of:

- unit tests for changed business logic
- integration or boundary test for changed interfaces
- smoke build/run verification when tests are unavailable

Additionally, one representative negative-path check MUST be present for changed behavior.

### FMPH2-3 Hard fail criteria (binding)

Gate result MUST be `fail` if any applies:

- no executed verification evidence exists
- changed behavior has no test or smoke verification path
- no recovery/rollback guidance is documented for non-trivial changes
- decisions are made without recorded rationale in docs/ADR equivalent

### FMPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps:

- `WARN-FALLBACK-BASELINE-UNKNOWN`
- `WARN-FALLBACK-TESTING-INSUFFICIENT`
- `WARN-FALLBACK-RECOVERY-UNSPECIFIED`
