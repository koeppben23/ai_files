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
