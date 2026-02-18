# Frontend Angular + Nx Profile Rulebook (v2.0)

This profile defines stack-specific governance for Angular frontends in an Nx monorepo.
It is applied in addition to:
- `master.md` (phases, gates, activation)
- `rules.md` (core engineering governance)

## Intent (binding)

Produce top-tier frontend business behavior and tests by deterministic patterns and evidence, not by style preference.

## Scope (binding)

Angular+Nx architecture boundaries, state patterns, contract-driven UI integration, and deterministic frontend test quality.

## Activation (binding)

This profile applies when Angular+Nx stack evidence is selected by governance profile detection (explicit user choice or deterministic discovery).

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
For Angular+Nx behavior, this profile governs stack-specific rules and activated addons/templates may refine within profile constraints.

## Phase integration (binding)

- Phase 2: lock repo conventions, state patterns, and addon requirements.
- Phase 4: apply profile constraints and required templates/addons to changed scope.
- Phase 5/6: verify evidence-backed quality gates, including deterministic frontend tests.

## Evidence contract (binding)

- Every non-trivial quality claim MUST map to BuildEvidence.
- Missing evidence MUST be reported as `not-verified` and cannot support gate pass claims.

## Tooling (binding)

- Use repo-native Nx commands for lint/test/build/e2e where available.
- Non-runnable tooling in current host MUST be reported with recovery commands and `not-verified` claims.

---

## Templates Addon (Binding)

For `frontend-angular-nx`, deterministic generation requires:
- `rules.frontend-angular-nx-templates.md`

Binding:
- At code-phase (Phase 4+), the workflow MUST load the templates addon and record it in:
  - `SESSION_STATE.LoadedRulebooks.templates`
- The load evidence MUST include resolved path plus version/digest evidence when available:
  - `SESSION_STATE.RulebookLoadEvidence.templates`
- If required and missing at code-phase, apply canonical required-addon policy from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`.
- This profile MUST NOT redefine blocking semantics.

When loaded, templates are binding defaults. If a template conflicts with locked repo conventions, apply the minimal convention-aligned adaptation and record the deviation.

---

## Addon Policy Classes (Binding)

- Addon class semantics are canonical in `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`; this profile MUST reference, not redefine, those semantics.
- Addon manifests/rulebooks MUST declare `addon_class` explicitly.
- This profile may define frontend-specific required-signal logic, but missing-rulebook handling MUST follow canonical policy.

---

## 1. Stack Identification (Applicability)

This profile applies when repository evidence indicates Angular + Nx, typically:
- `nx.json` present
- Angular workspace signals (`angular.json`, Angular builders, or Angular source imports)
- `apps/` + `libs/` monorepo structure

If stack does not match, switch profile; do not force Angular patterns into another stack.

---

## 2. Repo Conventions Lock (Binding)

Before code changes, detect and lock in `SESSION_STATE`:
- Angular major version and standalone vs NgModule convention
- State pattern (signals/store/component-store/ngrx) and selector style
- HTTP/data-access pattern (direct HttpClient vs generated API client)
- Form strategy (typed reactive forms, validators, error rendering)
- Testing stack (Jest/Karma, Testing Library, Cypress/Playwright)
- Styling pattern (SCSS/CSS/Tailwind/design-system primitives)
- Nx project boundaries and tag constraints

Rule: once detected, these become constraints. If unknown, mark unknown and avoid introducing a new architecture pattern.

---

## 3. Canonical Commands (Evidence-Aware)

Use repo-native Nx targets when present; otherwise nearest equivalent:
- Install: `npm ci`
- Lint: `npx nx affected -t lint`
- Unit/integration tests: `npx nx affected -t test`
- Build: `npx nx affected -t build`
- E2E: `npx nx affected -t e2e`

Build/test success claims are invalid without BuildEvidence captured in `SESSION_STATE`.

---

## 4. Architecture and Boundaries (Binding)

- Respect `apps/*` vs `libs/*` layering and tag constraints.
- Shared code belongs in `libs/*`; avoid app-to-app leakage.
- Use workspace aliases; avoid deep relative imports that bypass boundaries.
- New domain capability SHOULD be implemented as feature/data-access/ui libraries, not as app-local sprawl.

Hard fail conditions:
- boundary rule violations
- cross-layer imports that circumvent Nx constraints
- introducing a second state architecture without repo evidence

---

## 5. Angular Implementation Standards (Binding)

### 5.1 Components
- MUST keep components focused: presentational vs container responsibilities.
- MUST NOT place heavy computations and imperative orchestration in templates.
- SHOULD use explicit inputs/outputs and typed view models.

### 5.2 Change detection and reactivity
- Preserve repo default strategy.
- Use deterministic reactive composition; avoid nested subscriptions.
- SHOULD use `async` pipe, signals, or repo-standard teardown strategy.

### 5.3 Forms and validation
- Use repo form pattern (typed reactive forms if present).
- Validation messages and error states MUST be predictable and testable.

### 5.4 API boundaries
- MUST keep transport DTOs at boundaries; map to view/domain models.
- MUST NOT leak raw backend payload shapes through UI layers.

### 5.5 Security and privacy
- No secrets/PII in logs.
- Safe HTML binding and DOM operations (XSS-aware).
- Preserve existing CSP/security posture.

---

## 6. Contract and Codegen Alignment (Binding if present)

If repo uses OpenAPI/TS client generation:
- treat spec/generator output as boundary contract
- do not hand-edit generated artifacts
- regenerate via repo-native scripts and include evidence

If no generator exists, do not invent one unless requested.

---

## 7. Test Rules (Top-Tier, Binding)

### 7.1 Unit/component tests
- Deterministic and behavior-focused.
- SHOULD test user-visible outcomes over implementation internals.
- MUST NOT rely on low-signal assertions (`truthy`/snapshot spam).

### 7.2 Integration tests
- Cover state transitions, async boundaries, and form/validation behavior.
- Mock only external edges; keep core behavior realistic.

### 7.3 E2E tests (if established)
- Cover critical user journeys.
- Use stable selectors (`data-testid` or repo standard).
- No fixed sleeps; bounded polling/waits only.

### 7.4 Advanced test excellence (binding when applicable)
- Concurrency/async determinism: for retries/debounced flows/cache invalidation, include at least one deterministic async scenario.
- Contract-negative tests: for API-driven UI, include at least one malformed/error-path assertion at UI boundary.
- Property/invariant tests: for non-trivial transforms/selectors, include at least one invariant-style test when tooling supports it.

---

## 8. Frontend Quality Gates (Hard Fail)

Change fails if any applies:

### FQG-1 Build/Lint Gate
- affected build/lint fails

### FQG-2 Boundary Gate
- Nx/project boundary violations

### FQG-3 Test Quality Gate
- missing deterministic tests for changed behavior
- flaky async behavior or unbounded waits
- missing required negative-path coverage

### FQG-4 Contract Gate (if contracts exist)
- contract/client drift without explicit approval
- edited generated client code

### FQG-5 Accessibility/UX Safety Gate
- obvious a11y regressions in changed flows (roles/labels/focus/keyboard)

### FQG-6 Performance Safety Gate (if tooling exists)
- material regression in bundle/perf budget without approval and mitigation

---

## 9. BuildEvidence Requirements (Binding)

Claims like these require evidence snippets in `SESSION_STATE.BuildEvidence`:
- "tests are green"
- "no boundary violations"
- "no contract drift"
- "a11y/perf unchanged"

If evidence is missing, status is "not verified" and the change cannot be considered done.

---

## 10. Definition of Done (Binding)

Frontend Angular + Nx change is DONE only if:
- quality gates pass
- changed behavior is covered by deterministic tests
- boundaries and conventions remain intact
- contract/codegen rules are respected when applicable
- BuildEvidence exists for all quality claims

If any item is missing -> NOT DONE.

## 11. Examples (GOOD/BAD)

GOOD:
- Feature flow implemented across `libs/<domain>/feature`, `libs/<domain>/data-access`, and `libs/<domain>/ui` with valid Nx boundaries.

BAD:
- App-level component imports deep files from another app, bypassing Nx/tag constraints.

GOOD:
- Existing repo state pattern is preserved (for example signals store) and new selectors remain deterministic.

BAD:
- Mixed state architecture introduced ad hoc (signals + ngrx reducers) without repo evidence.

GOOD:
- Changed async UI path has one deterministic negative-path test and uses stable `data-testid` selectors.

BAD:
- E2E relies on fixed waits and brittle CSS-chain selectors for changed critical journey.

## 12. Troubleshooting

1) Symptom: Nx boundary errors on lint/test
- Cause: cross-layer imports or missing library split
- Fix: move code into proper `feature/data-access/ui` libs and restore tag-safe imports.

2) Symptom: Store/signals behavior regresses after change
- Cause: new state pattern introduced instead of reusing repo convention
- Fix: refactor to existing pattern and add deterministic state-transition tests.

3) Symptom: Frontend tests flaky in CI
- Cause: unbounded waits or missing deterministic network control
- Fix: use retryable assertions/intercepts, remove fixed sleeps, and verify stable selectors.

---

## Angular-Nx Principal Hardening v2 (Binding)

This section defines Angular+Nx-specific, measurable hardening rules for frontend code and tests.

### ANPH2-1 Risk tiering by touched surface (binding)

The workflow MUST classify changed scope before implementation and gate reviews
using the canonical tiering contract from `rules.risk-tiering.md` (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`).

`ANPH2` adds Angular-specific obligations per canonical tier; it does not define a parallel tier system.

### ANPH2-2 Mandatory evidence pack per tier (binding)

For `TIER-LOW` (per canonical tiering), evidence requires:
- build + lint pass
- changed-module tests

For `TIER-MEDIUM`, evidence requires:
- build + lint pass
- changed-module tests
- at least one negative-path test for changed UI behavior

For `TIER-HIGH`, evidence requires:
- build + lint pass
- changed-module tests
- boundary/contract checks (if codegen present)
- one deterministic negative-path test and one deterministic async/state-transition test (as applicable)

### ANPH2-3 Hard fail criteria for principal acceptance (binding)

An Angular+Nx change MUST be marked `fail` in P5.3/P6 if any applies:

- `ANPH2-FAIL-01`: no evidenceRef for a critical claim
- `ANPH2-FAIL-02`: Nx boundary violation detected
- `ANPH2-FAIL-03`: changed UI behavior without deterministic test coverage
- `ANPH2-FAIL-04`: generated client code modified by hand
- `ANPH2-FAIL-05`: flaky async test behavior (fixed sleeps, unbounded waits)

### ANPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps:

- `WARN-ANGULAR-BOUNDARY-DRIFT`: Nx tag/project boundary mismatch — recovery: align project tags and imports
- `WARN-ANGULAR-STATE-PATTERN-MIX`: multiple state patterns detected without repo evidence — recovery: consolidate to repo-standard pattern
- `WARN-ANGULAR-ASYNC-DETERMINISM`: async test without deterministic control — recovery: add explicit timing/mock control

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
