# rules.frontend-angular-nx.md
Frontend Profile Rulebook — Angular + Nx (Monorepo)

This profile defines **stack-specific** rules for Angular frontends in an Nx monorepo.
It must be used together with:
- `master.md` (process / phases / gates)
- `rules.md` (core technical governance)

If this profile conflicts with `master.md` or `rules.md`, this profile is subordinate.

---

## 1. Stack Identification (Applicability)

This profile applies if the repository shows most of:
- `nx.json` present (Nx workspace)
- `apps/` and `libs/` structure
- Angular dependencies (e.g. `@angular/core`, `@angular/cli`)
- TypeScript configs with Angular compiler options and `strict` mode

If the stack does not match, stop and request a profile switch.

---

## 2. Tooling & Canonical Commands (Evidence-Aware)

### 2.1 Install
Preferred:
- `npm ci`

### 2.2 Lint / Format
Preferred (Nx):
- `npx nx affected -t lint`
Or per project:
- `npx nx lint <project>`

Formatting must follow repository configuration (Prettier).
Do not introduce a new formatter or style tool unless explicitly requested.

### 2.3 Unit / Integration Tests
Preferred (Nx + Jest):
- `npx nx affected -t test`
Or per project:
- `npx nx test <project>`

### 2.4 Build
Preferred:
- `npx nx affected -t build`
Or:
- `npx nx build <project>`

### 2.5 E2E
Preferred:
- `npx nx affected -t e2e`
Or:
- `npx nx e2e <project>`

Build/test success claims require BuildEvidence (per `rules.md`).

---

## 3. Architecture & Project Boundaries (Nx)

- Respect `apps/*` vs `libs/*` layering.
- Shared code belongs in `libs/*` (shared/core, shared/ui, shared/utils, etc.).
- Do not create cross-layer imports that bypass library boundaries.
- Prefer path aliases (from `tsconfig.base.json`) over deep relative paths.

When adding new features:
- prefer a new `libs/<scope>/feature/<feature-name>` library rather than bloating apps.

---

## 4. TypeScript & Angular Strictness (Binding)

- TypeScript must remain strict (no weakening of strict flags).
- Angular compiler strictness must not be reduced:
  - `strictTemplates`, `strictInjectionParameters`, etc.

Disallowed:
- `any` unless justified and narrowly scoped
- disabling strict mode to “make it compile”

Prefer:
- precise types
- typed wrappers for external/legacy data
- exhaustive handling for unions/enums

---

## 5. Angular Coding Standards

### 5.1 Components
- Follow existing repository patterns (standalone vs. NgModule).
- Keep components small and focused:
  - presentational components: inputs/outputs, no data fetching
  - container components: orchestration, route/data wiring

### 5.2 Dependency Injection
- Prefer constructor injection / `inject()` as per repo style.
- Avoid service locators and manual global singletons.

### 5.3 Change Detection & Performance
- Follow repo defaults.
- Use performance-oriented patterns where applicable:
  - avoid heavy computations in templates
  - prefer memoized selectors / computed values
  - avoid nested subscriptions in components

### 5.4 RxJS
- Avoid subscription leaks:
  - prefer `async` pipe, `takeUntilDestroyed`, or equivalent repo pattern
- Avoid nested `subscribe` anti-patterns.
- Handle error paths explicitly (do not swallow errors).

---

## 6. Routing, Forms, i18n, and UI Consistency

- Routing: align with existing route structure and guards/resolvers.
- Forms: use the existing forms library/patterns from the repo (typed forms if present).
- i18n: follow repo conventions (e.g., translation keys, namespaces, loader).
- UI: reuse shared UI libraries (`libs/shared/ui`, etc.) rather than duplicating components.

---

## 7. API / Contract / Codegen (If Present)

If OpenAPI code generation scripts exist in the repo:
- Prefer using the existing generators (do not handwrite generated clients/models).
- Any change affecting generated artifacts must include:
  - updated generator inputs (specs)
  - a reproducible generation step documented in the plan
  - updated snapshots if the repo uses snapshot generation

If the repo does not contain OpenAPI/codegen:
- mark as N/A (do not invent).

---

## 8. Testing Standards (Jest + Cypress)

### 8.1 Unit/Integration Tests (Jest)
- Tests must be deterministic.
- Prefer:
  - clear arrange/act/assert structure
  - testing public behavior rather than implementation details
- Avoid brittle DOM tests; prefer Angular testing utilities aligned with the repo.

Anti-patterns (examples):
- snapshot spam without intent
- tests that only assert “is truthy” / “not null”
- disabling strict typing in tests to “get it working”

### 8.2 E2E (Cypress)
- E2E tests should cover user flows, not internal implementation.
- Avoid flaky selectors:
  - prefer stable `data-testid` (if repo uses it) or robust semantic selectors.

---

## 9. Security & Privacy (Frontend)

- Do not log secrets or PII.
- Do not persist sensitive tokens in insecure storage unless the repo explicitly does so and the change is ticket-approved.
- Ensure external links, HTML bindings, and dynamic DOM operations are safe (XSS-aware).
- Follow repo’s CSP/security headers configuration if present.

---

## 10. Output Expectations (Profile-Specific)

When proposing changes:
- list impacted apps/libs and where changes will live
- ensure the Change Matrix includes:
  - Internal API / Ports
  - Configuration / Feature Flags (if used)
  - Rollout/Migration Strategy (for breaking UI changes or feature flags)
  - Observability/Monitoring (if relevant)

This profile must not override output limits from `rules.md`.

---
