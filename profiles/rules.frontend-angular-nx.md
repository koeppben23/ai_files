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

## 2a. Decision Trees (Binding)

The following decision trees guide architecture-level decisions for Angular/Nx projects. The assistant MUST follow these trees and record the decision path in the plan.

### DT-NG1: State Management Selection

When implementing state management for a new feature:

```
START -> Does the repo already use a state management pattern?
  YES -> Follow detected pattern (signals/NgRx/component-store). STOP.
         Reason: Mixing state patterns is anti-pattern AP-NG02.
  NO  -> Is the state local to a single component or feature?
    YES -> Is it simple UI state (toggle, form state, loading indicator)?
      YES -> Component-local signals or simple properties.
             Reason: No overhead; state is contained.
      NO  -> Component Store (@ngrx/component-store or signal-based equivalent).
             Reason: Encapsulated, testable, no global side effects.
    NO  -> Is the state shared across multiple features/routes?
      YES -> Does the app require complex async flows (optimistic updates, caching, undo)?
        YES -> NgRx Store (actions/reducers/effects/selectors).
               Reason: Predictable state transitions, time-travel debugging, effect isolation.
        NO  -> Signals-based facade service (injectable, reactive).
               Reason: Simpler than NgRx, sufficient for shared read/write state.
      NO  -> Re-evaluate: if state is not local and not shared, clarify scope with user.
```

### DT-NG2: Test Type Selection

For each changed component, select appropriate test types:

```
START -> What type of component changed?
|
+-- Container / Smart component
|   -> Unit test (TestBed): verify delegation to facade/store/service
|   -> Test template bindings (essential ones): rendered output matches state
|   -> Mock all injected services; do not test child component internals
|
+-- Presentational / Dumb component
|   -> Unit test (TestBed): input/output behavior
|   -> Test: default rendering, input variations, event emission
|   -> No service mocking needed (presentational has no dependencies)
|
+-- Facade / Store / State management
|   -> Unit test: state transitions, selector outputs, effect triggers
|   -> For NgRx: test reducer (pure function), selectors, effects separately
|   -> For Component Store: test updaters, selectors, effects
|   -> For signal facades: test computed signals and state mutations
|
+-- API boundary service
|   -> Unit test: request construction, response mapping, error handling
|   -> Mock HttpClient (HttpClientTestingModule)
|   -> Test: success path, error mapping, retry logic if present
|
+-- Guard / Interceptor
|   -> Unit test: routing decisions / request transformation
|   -> Test: allowed, denied, redirect scenarios
|   -> For interceptors: verify header injection, error interception
|
+-- Pipe / Directive
|   -> Unit test: transform logic (pipes are pure functions)
|   -> Component test (directives): host component with applied directive
|
+-- E2E / Cross-feature flows
   -> Only if established in the repo (Cypress/Playwright)
   -> Cover critical user journeys, not individual components
```

### DT-NG3: Library Type Selection (Nx)

When creating a new Nx library:

```
START -> What is the primary purpose of the new code?
|
+-- UI components (shared across features)
|   -> Type: ui library
|   -> Location: libs/shared/ui/{name}
|   -> Tags: type:ui, scope:shared
|   -> Contains: presentational components, pipes, directives only
|   -> Must NOT import from feature or data-access libraries
|
+-- Data access (API calls, state management for a domain)
|   -> Type: data-access library
|   -> Location: libs/{domain}/data-access
|   -> Tags: type:data-access, scope:{domain}
|   -> Contains: services, facades/stores, models/DTOs, API clients
|
+-- Feature (routed page, smart components, feature-specific logic)
|   -> Type: feature library
|   -> Location: libs/{domain}/feature-{name}
|   -> Tags: type:feature, scope:{domain}
|   -> Contains: container components, routing, feature-specific presentational components
|   -> May import: data-access (same domain), ui (shared)
|
+-- Pure utility (formatting, validation, math, constants)
|   -> Type: util library
|   -> Location: libs/shared/util/{name}
|   -> Tags: type:util, scope:shared
|   -> Contains: pure functions, no Angular dependencies if possible
|   -> Must NOT import from any other library type
|
+-- Does the code belong to an existing library?
   -> Add to existing library. Do NOT create a new one. STOP.
      Follow existing library structure and barrel exports.
```

### DT-NG4: Component Type Decision

When creating a new component:

```
START -> Does the component manage state or orchestrate behavior?
  YES -> Container (smart) component.
         Inject facade/store/service. Delegate all logic.
         Template calls presentational children via inputs/outputs.
  NO  -> Does it render UI based purely on inputs?
    YES -> Presentational (dumb) component.
           @Input() for data, @Output() for events. No injected services.
           Use OnPush change detection.
    NO  -> Is it a form?
      YES -> Form component (may be smart or dumb depending on context).
             Use typed reactive forms (FormGroup<T>).
             Validation logic in validators, not in template.
      NO  -> Is it a layout/structural element?
        YES -> Layout component. Minimal logic, uses <ng-content> projection.
        NO  -> Clarify purpose with user before proceeding.
```

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

### 5.6 Naming Conventions (Binding)

The following naming conventions are binding unless repo conventions explicitly differ (in which case, follow repo conventions and record deviation).

**Files and directories:**

| Type | Convention | Example |
|------|-----------|---------|
| Component | `{feature}-{type}.component.ts` | `user-page.component.ts`, `user-view.component.ts` |
| Service/Facade | `{feature}.facade.ts`, `{feature}.service.ts` | `user.facade.ts` |
| API boundary | `{feature}.api.ts` | `user.api.ts` |
| Store (NgRx) | `{feature}.actions.ts`, `{feature}.reducer.ts`, `{feature}.effects.ts`, `{feature}.selectors.ts` | `user.actions.ts` |
| Component Store | `{feature}.store.ts` | `user.store.ts` |
| Guard | `{feature}.guard.ts` or `auth.guard.ts` | `auth.guard.ts` |
| Interceptor | `{feature}.interceptor.ts` or `auth.interceptor.ts` | `auth.interceptor.ts` |
| Model/interface | `{feature}.model.ts` | `user.model.ts` |
| Test | `{source-file}.spec.ts` | `user.facade.spec.ts` |

**Classes and symbols:**

| Type | Convention | Example |
|------|-----------|---------|
| Container component | `{Feature}PageComponent` | `UserPageComponent`, `OrderPageComponent` |
| Presentational component | `{Feature}ViewComponent`, `{Feature}ListComponent` | `UserViewComponent` |
| Form component | `{Feature}FormComponent` | `UserFormComponent` |
| Facade | `{Feature}Facade` | `UserFacade`, `OrderFacade` |
| API service | `{Feature}Api` | `UserApi`, `OrderApi` |
| Component Store | `{Feature}Store` | `UserStore` |
| NgRx actions | `{Feature}Actions` (via `createActionGroup`) | `UserActions` |
| NgRx reducer | `{feature}Reducer` | `userReducer` |
| NgRx effects | `{Feature}Effects` | `UserEffects` |
| Guard function | `{feature}Guard`, `authGuard`, `roleGuard` | `authGuard` |
| Interceptor function | `{feature}Interceptor`, `authInterceptor` | `authInterceptor` |
| View model | `{Feature}ViewModel` | `UserViewModel` |
| State interface | `{Feature}State` | `UserState` |

**Selectors:**

| Type | Convention | Example |
|------|-----------|---------|
| Component selector | `app-{feature}-{type}` | `app-user-page`, `app-user-view` |

**Methods and properties:**

| Type | Convention | Example |
|------|-----------|---------|
| Event handler | `on{Action}()` | `onRefresh()`, `onSubmit()`, `onDelete()` |
| View model | `vm` (signal) or `vm$` (observable) | `readonly vm = this.facade.vm` |
| NgRx selectors | `select{Feature}{Property}` | `selectUserItems`, `selectUserLoading` |
| NgRx action events | Natural language in `createActionGroup` | `'Load Users'`, `'Create User Success'` |
| Store updater | `set{Property}` | `setLoading`, `setItems` |
| Store effect | `load{Feature}s`, `create{Feature}` | `loadUsers`, `createUser` |

**Test naming:**

| Type | Convention | Example |
|------|-----------|---------|
| `describe` block | Class or function name | `describe('UserFacade', ...)` |
| `it` block | Behavior description | `it('should expose loaded items', ...)` |
| Spy object | `jasmine.createSpyObj('{Class}', [...])` | `jasmine.createSpyObj('UserApi', ['fetchAll'])` |

**Nx library naming:**

| Type | Convention | Example |
|------|-----------|---------|
| Feature lib | `libs/{domain}/feature-{name}` | `libs/user/feature-list` |
| Data access lib | `libs/{domain}/data-access` | `libs/user/data-access` |
| UI lib | `libs/{domain}/ui` | `libs/user/ui` |
| Util lib | `libs/{domain}/util` or `libs/shared/util-{name}` | `libs/shared/util-date` |

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

---

## 11.1 Anti-Patterns Catalog (Binding)

Each anti-pattern below includes an explanation of **why** it is harmful. The assistant MUST avoid generating code that matches these anti-patterns and MUST flag them during plan review and code review.

### AP-NG01: Business Logic in Components

**Pattern:** Component class contains domain calculations, validation logic, or complex conditional branching beyond simple UI state.

**Why it is harmful:**
- Components become untestable without full Angular TestBed setup and DOM rendering.
- Logic cannot be reused across components or triggered from non-UI contexts.
- Mixing concerns makes components large and difficult to reason about.

**Detection:** Component methods with domain calculations, API calls, or multi-step conditional logic not related to template rendering.

---

### AP-NG02: Mixed State Architectures

**Pattern:** Introducing NgRx reducers in a codebase that uses signals, or adding signals in an NgRx codebase, without explicit repo-level decision.

**Why it is harmful:**
- Creates two incompatible mental models: developers must understand and maintain two state systems.
- State synchronization between the two systems becomes a source of bugs.
- Doubles the test surface: both state systems need independent test coverage.

**Detection:** Imports from `@ngrx/store` and Angular `signal()` in the same feature module without documented architectural decision.

---

### AP-NG03: Direct HttpClient in Components

**Pattern:** Component injects `HttpClient` directly instead of going through an API boundary service.

**Why it is harmful:**
- Scatters API knowledge (URLs, headers, DTO shapes) across components.
- Makes DTO-to-view-model mapping inconsistent: each component maps differently.
- Makes testing expensive: every component test needs `HttpTestingController`.
- Backend API changes require touching every component that calls the API.

**Detection:** `HttpClient` in component constructor/inject; `this.http.get(...)` calls in component methods.

---

### AP-NG04: Leaked Backend DTOs in UI

**Pattern:** Backend response types used directly in component templates, facades, or stores without explicit mapping.

**Why it is harmful:**
- Couples the UI to the backend's internal data structure: backend renames break the entire frontend.
- Backend-specific fields (internal IDs, audit timestamps, database enums) leak into UI concerns.
- Makes frontend tests brittle: test data must match backend structure exactly.

**Detection:** API response types used as `@Input()` types or facade return types without a mapping step.

---

### AP-NG05: Nested Subscriptions

**Pattern:** Subscribing to an Observable inside another subscription callback.

**Why it is harmful:**
- Creates memory leaks: inner subscriptions are not automatically cleaned up.
- Makes error handling unpredictable: errors in inner streams don't propagate to outer handlers.
- Creates race conditions: inner subscriptions may fire after the outer context is stale.
- Violates reactive composition: operators like `switchMap`, `mergeMap`, `concatMap` exist for this purpose.

**Detection:** `.subscribe(() => { someObs$.subscribe(...) })` patterns in component or service code.

---

### AP-NG06: Fixed Waits in Tests

**Pattern:** Using `setTimeout()`, `tick(5000)`, or `cy.wait(5000)` with arbitrary durations in tests.

**Why it is harmful:**
- Flaky: the wait may be too short on slow CI runners, causing intermittent failures.
- Slow: the wait is always the maximum duration even when the operation completes instantly.
- Masks real bugs: the test might pass only because the wait covers up a timing issue.

**Detection:** `setTimeout` in test code; `tick()` with large values not tied to specific timer-based logic; `cy.wait(number)` in E2E tests.

---

### AP-NG07: Untyped Reactive Forms

**Pattern:** Using untyped `FormGroup` (without generic parameter) and accessing form values without type safety.

**Why it is harmful:**
- No compile-time checks on form field names: typos in `form.get('emial')` are only caught at runtime.
- No type inference on `.value`: all values are `any`, bypassing TypeScript's type system.
- Angular 14+ supports typed forms natively; untyped forms are a legacy pattern.

**Detection:** `new FormGroup({...})` without type parameter; `form.get('fieldName')` instead of `form.controls.fieldName`; `form.value` used without type assertion.

---

### AP-NG08: Component Without OnPush

**Pattern:** Components using the default `ChangeDetectionStrategy.Default` instead of `OnPush`.

**Why it is harmful:**
- Default change detection runs on every event (click, timer, HTTP response) across the entire component tree.
- Causes performance degradation as the component tree grows.
- Hides reactivity bugs: components re-render even when their inputs haven't changed.

**Detection:** Component decorator without `changeDetection: ChangeDetectionStrategy.OnPush` property.

---

### AP-NG09: Class-Based Guards and Interceptors

**Pattern:** Using class-based `CanActivate` or `HttpInterceptor` interfaces instead of functional equivalents.

**Why it is harmful:**
- Class-based guards and interceptors are deprecated in modern Angular.
- They require unnecessary boilerplate (class declaration, interface implementation, provider registration).
- Functional equivalents are simpler, tree-shakable, and align with Angular's functional API direction.

**Detection:** Classes implementing `CanActivate`, `CanDeactivate`, `HttpInterceptor` interfaces; `{ provide: HTTP_INTERCEPTORS, useClass: ... }` in providers.

---

### AP-NG10: Cross-App Imports in Nx Monorepo

**Pattern:** One app directly imports from another app's source code instead of going through shared libraries.

**Why it is harmful:**
- Violates Nx boundary rules: apps should be independent deployment units.
- Creates circular dependency risks between apps.
- Makes it impossible to build/test/deploy apps independently.
- Shared logic belongs in `libs/` where it can be versioned and boundary-tagged.

**Detection:** Import paths like `apps/other-app/src/...` in any source file; Nx boundary lint rule violations.

---

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
