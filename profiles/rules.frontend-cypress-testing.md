# Frontend Cypress Testing Addon

Addon class (binding): advisory addon.

Purpose: strengthen frontend E2E quality and reduce flakiness when Cypress is present.

Non-blocking policy: if context/tooling is incomplete, emit WARN with recovery steps and continue conservatively.

## Binding guidance

- Prefer deterministic network control (`cy.intercept`) for changed critical flows.
- Use stable selectors (`data-testid` or repo standard), not fragile CSS chains.
- No fixed sleeps (`cy.wait(<ms>)`) except explicitly justified external constraints.
- Assertions target user-visible outcomes, not implementation internals.

## Suggested warnings

- `WARN-CYPRESS-FLAKY-RISK`
- `WARN-CYPRESS-SELECTOR-UNSTABLE`
- `WARN-CYPRESS-NO-CRITICAL-FLOW-COVERAGE`

## Recovery steps template

1. Stabilize selectors in changed screens.
2. Add/adjust intercept fixtures for critical path.
3. Replace fixed waits with retryable assertions.

END OF ADDON

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

## Principal Hardening v2 - Cypress Critical Quality (Binding)

### CPH2-1 Required scorecard criteria (binding)

When Cypress scope is touched, the scorecard MUST evaluate and evidence:

- `CYPRESS-CRITICAL-FLOW-COVERAGE`
- `CYPRESS-SELECTOR-STABILITY`
- `CYPRESS-NETWORK-DETERMINISM`
- `CYPRESS-NO-FIXED-SLEEPS`
- `CYPRESS-ERROR-PATH-PROOF`

Each criterion MUST include an `evidenceRef`.

### CPH2-2 Required test matrix (binding)

For changed user-facing behavior, Cypress evidence MUST include at least:

- one critical happy-path journey
- one representative negative/error path
- one async synchronization assertion without fixed millisecond sleeps

If a row is not applicable, explicit rationale is required.

### CPH2-3 Hard fail criteria (binding)

Gate result MUST be `fail` if any applies:

- no critical flow coverage for changed behavior
- unstable selectors (fragile CSS chain/XPath) when stable selector convention exists
- fixed sleep used as primary sync mechanism
- no negative-path assertion for changed API-driven UI behavior

### CPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps when advisory handling remains non-blocking:

- `WARN-CYPRESS-NETWORK-CONTROL-MISSING`
- `WARN-CYPRESS-CRITICAL-PATH-MISSING`
- `WARN-CYPRESS-ASYNC-FLAKE-RISK`

---

## Principal Hardening v2.1 - Standard Risk Tiering (Binding)

### RTN-1 Canonical tiers (binding)

All addon/template assessments MUST use this canonical tier syntax:

- `TIER-LOW`: local/internal changes with low blast radius and no external contract or persistence risk.
- `TIER-MEDIUM`: behavior changes with user-facing, API-facing, or multi-module impact.
- `TIER-HIGH`: contract, persistence/migration, messaging/async, security, or rollback-sensitive changes.

If uncertain, choose the higher tier.

### RTN-2 Tier evidence minimums (binding)

- `TIER-LOW`: build/lint (if present) + targeted changed-scope tests.
- `TIER-MEDIUM`: `TIER-LOW` evidence + at least one negative-path assertion for changed behavior.
- `TIER-HIGH`: `TIER-MEDIUM` evidence + one deterministic resilience/rollback-oriented proof (retry/idempotency/recovery/concurrency as applicable).

### RTN-3 Tier-based gate decisions (binding)

- A gate result cannot be `pass` when mandatory tier evidence is missing.
- For advisory addons, missing tier evidence remains non-blocking but MUST emit WARN + recovery and result `partial` or `fail`.
- For required addons/templates, missing `TIER-HIGH` evidence MAY block code-phase per master/core/profile policy.

### RTN-4 Required SESSION_STATE shape (binding)

```yaml
SESSION_STATE:
  RiskTiering:
    ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
    Rationale: "short evidence-based reason"
    MandatoryEvidence:
      - EV-001
      - EV-002
    MissingEvidence: []
```

### RTN-5 Unresolved tier handling (binding)

If tier cannot be determined from available evidence, set status code `WARN-RISK-TIER-UNRESOLVED`, provide a conservative default (`TIER-HIGH`), and include recovery steps to refine classification.

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

Non-critical criteria MAY exist, but cannot compensate for a failed critical criterion.

### CAL-3 Tier score thresholds (binding)

A principal-grade gate result MAY be `pass` only if all conditions are true:

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

If scorecard data is incomplete or non-comparable, emit `WARN-SCORECARD-CALIBRATION-INCOMPLETE` and block principal-grade declaration (`not-verified`).

