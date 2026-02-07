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

## Shared Principal Governance Contracts (Binding)

This rulebook uses shared advisory governance contracts:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior:

- When this rulebook is active in execution/review phases, load these as advisory governance contracts.
- Record when loaded:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- If one of these shared rulebooks is unavailable, emit WARN + recovery, mark affected claims as
  `not-verified`, and continue conservatively.
