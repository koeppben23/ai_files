# Frontend Angular + Nx Profile Rulebook (v2.0)

This profile defines stack-specific governance for Angular frontends in an Nx monorepo.
It is applied in addition to:
- `master.md` (phases, gates, activation)
- `rules.md` (core engineering governance)

Priority order on conflict:
`master.md` > `rules.md` (core) > this profile.

Intent (binding): produce top-tier frontend business behavior and tests by deterministic patterns and evidence, not by style preference.

---

## Templates Addon (Binding)

For `frontend-angular-nx`, deterministic generation requires:
- `rules.frontend-angular-nx-templates.md`

Binding:
- At code-phase (Phase 4+), the workflow MUST load the templates addon and record it in:
  - `SESSION_STATE.LoadedRulebooks.templates`
- If required and missing at code-phase: `Mode = BLOCKED`, `Next = BLOCKED-MISSING-TEMPLATES`.

When loaded, templates are binding defaults. If a template conflicts with locked repo conventions, apply the minimal convention-aligned adaptation and record the deviation.

---

## Addon Policy Classes (Binding)

- Required addons (code-generation-critical) may hard-block in code-phase when missing.
- Advisory addons (quality amplifiers) MUST emit WARN + recovery steps and continue conservatively.
- Addon manifests/rulebooks MUST declare `addon_class` explicitly.

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
- Keep components focused: presentational vs container responsibilities.
- Avoid heavy computations and imperative orchestration in templates.
- Prefer explicit inputs/outputs and typed view models.

### 5.2 Change detection and reactivity
- Preserve repo default strategy.
- Use deterministic reactive composition; avoid nested subscriptions.
- Prefer `async` pipe, signals, or repo-standard teardown strategy.

### 5.3 Forms and validation
- Use repo form pattern (typed reactive forms if present).
- Validation messages and error states MUST be predictable and testable.

### 5.4 API boundaries
- Keep transport DTOs at boundaries; map to view/domain models.
- Do not leak raw backend payload shapes through UI layers.

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
- Prefer user-visible outcomes over implementation internals.
- Avoid low-signal assertions (`truthy`/snapshot spam).

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

---

Copyright (c) 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
