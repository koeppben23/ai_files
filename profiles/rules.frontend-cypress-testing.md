# Frontend Cypress Testing Addon

Addon class (binding): advisory addon.

## Intent (binding)

Strengthen frontend E2E quality and reduce flakiness when Cypress is present.

## Scope (binding)

Changed user-facing journeys, Cypress selector/network synchronization strategy, and E2E evidence quality.

Non-blocking policy: if context/tooling is incomplete, emit WARN with recovery steps and continue conservatively.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This advisory addon refines E2E-quality behavior and MUST NOT override `master.md`, `rules.md`, or active profile constraints.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/frontendCypress.addon.yml`.
This rulebook defines behavior once activated; it MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 2: record Cypress signals and runner evidence in `SESSION_STATE.AddonsEvidence.frontendCypress.signals`.
- Phase 2.1: decide critical journeys and flake controls for changed scope.
- Phase 4: implement/adjust deterministic Cypress coverage for changed behavior.
- Phase 5.3: execute repo-native e2e command or emit `not-verified` with recovery commands.

## Evidence contract (binding)

When active, maintain:
- `SESSION_STATE.AddonsEvidence.frontendCypress.required`
- `SESSION_STATE.AddonsEvidence.frontendCypress.signals`
- `SESSION_STATE.AddonsEvidence.frontendCypress.status` (`loaded|skipped|missing-rulebook`)
- warning codes in `warnings[]` for advisory flake/tooling uncertainty.

## Binding guidance

- SHOULD use deterministic network control (`cy.intercept`) for changed critical flows.
- Use stable selectors (`data-testid` or repo standard), not fragile CSS chains.
- No fixed sleeps (`cy.wait(<ms>)`) except explicitly justified external constraints.
- Assertions target user-visible outcomes, not implementation internals.

## Suggested warnings

- `WARN-CYPRESS-FLAKY-RISK`
- `WARN-CYPRESS-SELECTOR-UNSTABLE`
- `WARN-CYPRESS-NO-CRITICAL-FLOW-COVERAGE`

## Recovery template

1. Stabilize selectors in changed screens.
2. Add/adjust intercept fixtures for critical path.
3. Replace fixed waits with retryable assertions.

## Tooling (recommended)

Repo-native command hints:
- Nx workspace: `npx nx affected -t e2e`
- Cypress package script: `npm run cypress:run`
- Direct runner fallback: `npx cypress run`

## Examples (GOOD/BAD)

GOOD:
- `cy.intercept` controls changed API call and assertions verify user-visible outcomes with stable selectors.

BAD:
- `cy.wait(5000)` used as primary synchronization for changed critical flow.

## Troubleshooting

1) Symptom: tests pass locally but fail in CI intermittently
- Cause: missing deterministic network control
- Fix: add intercept fixtures and replace time-based waits with retryable assertions.

2) Symptom: selectors break after style refactor
- Cause: CSS-chain selectors coupled to layout
- Fix: switch to `data-testid` or repo-standard stable selector convention.

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

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
