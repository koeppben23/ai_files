# Cucumber BDD Addon Rulebook (v1.1)

This document defines the **Cucumber/BDD** addon rules.
It is applied **in addition** to the Core Rulebook (`rules.md`), the Master Prompt (`master.md`), and the active profile.

Priority order on conflict:
`master.md` > `rules.md` (Core) > active profile > this addon.

**Non-blocking policy:** This addon never hard-blocks progress. If required context, conventions, or tooling are missing/unclear, emit a **status code** with a concrete recovery action and continue with conservative defaults.

---

## 0. Core principle (binding)

> Feature files are **executable specifications**: stable, readable, and deterministic.
> Prefer **business semantics** (domain language) over implementation details.

**Binding rules:**
- Write scenarios so that they are deterministic across runs (no sleeps, no time-of-day dependencies, no shared mutable state).
- Prefer “Given/When/Then” that describe intent and observable outcomes, not internal method names.
- If implementation details are unavoidable, isolate them in step definitions, not in feature text.

---

## 1. Activation and evidence (binding)

**Separation of concerns:**
- **Activation signals** (how to detect Cucumber usage) belong to the addon manifest (`profiles/addons/cucumber.addon.yml`).
- This rulebook defines **behavior**, structure, and quality gates.

When this addon is active, the system MUST record evidence in Session State:

- `SESSION_STATE.AddonsEvidence.cucumber.required: boolean`
- `SESSION_STATE.AddonsEvidence.cucumber.signals: string[]`
- `SESSION_STATE.AddonsEvidence.cucumber.status: "loaded"|"skipped"|"missing-rulebook"|<warn-code>`

Suggested warn-codes for this addon:
- `WARN-CUCUMBER-VERSION-UNKNOWN`
- `WARN-CUCUMBER-RUNNER-UNKNOWN`
- `WARN-CUCUMBER-CONVENTIONS-UNKNOWN`
- `WARN-CUCUMBER-FLAKINESS-RISK`
- `WARN-CUCUMBER-NO-EVIDENCE`

---

## 2. Version and capability inference (binding)

The system SHOULD infer versions/capabilities automatically:

**Primary sources (prefer):**
- `pom.xml` / dependencyManagement (Cucumber BOM) → infer major/minor.
- `build.gradle` equivalents if present.
- Test runtime setup (JUnit Platform vs JUnit 4 runner).

If inference fails:
- Set `SESSION_STATE.AddonsEvidence.cucumber.status = WARN-CUCUMBER-VERSION-UNKNOWN`
- Continue using conservative assumptions:
  - Prefer JUnit Platform patterns (modern default)
  - Avoid framework-specific APIs that are version-sensitive

---

## 3. Phase integration

### Phase 1 — Discovery
When scanning the repo, collect:
- Feature file roots (`src/test/resources/**/*.feature`)
- Runner location(s) if present
- Step-definition package roots
- Evidence of glue configuration (JUnit, Spring context, etc.)

If no feature files are found but dependency suggests Cucumber:
- Mark `WARN-CUCUMBER-NO-EVIDENCE` and proceed (may be unused dependency).

### Phase 2 — Plan (required output)
For any ticket affecting behavior or tests, produce a Cucumber plan section:
- Which features/scenarios to add or update
- Step-definition strategy (reuse vs new)
- Test data strategy (fixtures, seed, cleanup)
- Execution strategy (tags, profiles, parallelization constraints)

### Phase 3 — Implementation (business + steps)
Implement:
- Feature updates
- Step definitions with clean glue boundaries
- Support utilities (test data builders, API clients, DB helpers) in test scope only

### Phase 5 — Verification
- Run relevant tagged subset first (fast feedback)
- Then full Cucumber suite or the repo’s standard test target
- If flaky behavior detected, record `WARN-CUCUMBER-FLAKINESS-RISK` with suspected causes and remediation

---

## 4. Conventions (binding)

### 4.1 Feature file structure
- Keep each feature focused on one capability (avoid “mega features”).
- Prefer 3–10 scenarios per feature, grouped by tags if necessary.
- Use **Background** sparingly (only for truly shared preconditions).
- Prefer **Scenario Outline** when it increases coverage without duplicating logic.

### 4.2 Step phrasing and granularity
- Steps MUST describe **observable behavior**.
- Avoid steps that do multiple actions at once.
- Avoid hard-coded IDs and timestamps; generate or look up deterministically.

**Good:**
- `Given a person exists with status "ACTIVE"`
- `When I request the person details`
- `Then the response contains the person status "ACTIVE"`

**Bad:**
- `Given I call createPersonAndActivateAndPublishKafkaEvent`

### 4.3 Step definitions (glue) design
- Keep step definitions thin:
  - parse input
  - call a small test helper/service
  - assert outputs
- Put heavy logic in reusable helpers under test scope.
- Ensure steps are **idempotent** where possible (safe retries).

### 4.4 Tags and execution
- Use tags to partition:
  - `@smoke`, `@regression`, `@wip`
  - `@slow`, `@integration`
  - environment tags if needed (`@local`, `@ci`)
- Provide a default tag strategy in the plan:
  - Ticket-related scenarios should be runnable as a small subset.

---

## 5. Determinism and anti-flakiness (binding)

### 5.1 Time and async behavior
- Do not use fixed sleeps for async waits.
- Use polling with bounded timeout and clear failure messages.
- Normalize time:
  - Use fixed clocks where available
  - Avoid “now()” in assertions unless explicitly controlled

### 5.2 Test data lifecycle
- Each scenario must own its data:
  - Create minimal needed entities
  - Clean up deterministically (transaction rollback, truncation strategy, or unique namespaces)
- For integration tests, prefer:
  - isolated schemas/namespaces
  - deterministic IDs or well-known keys

If data isolation is unclear:
- emit `WARN-CUCUMBER-CONVENTIONS-UNKNOWN` and choose the safest available approach (unique prefixes, cleanup hooks).

---

## 6. Reporting and failure diagnostics (binding)

On failure, the system SHOULD:
- Include step-level context (inputs sanitized)
- Capture the last request/response (or equivalent) for API tests
- Provide hints for common causes:
  - environment drift
  - missing seed data
  - async timing

If runner/tooling is unknown:
- emit `WARN-CUCUMBER-RUNNER-UNKNOWN` and document how to locate it (search for `@Cucumber` / `CucumberOptions` / `cucumber-junit-platform-engine`).

---

## 7. Quick checks (recommended)

Before finishing a ticket:
- Ensure new/changed scenarios run in isolation.
- Ensure tags are applied consistently.
- Ensure step definitions avoid duplication (prefer reuse).
- Ensure assertions validate domain outcomes, not incidental formatting.

---

## 8. Minimal recovery playbook (non-blocking)

If you hit unclear repo conventions:
1) Search for existing feature patterns and runner configuration.
2) Reuse existing tags and glue conventions.
3) If still unclear, choose conservative defaults and emit:
   - `WARN-CUCUMBER-CONVENTIONS-UNKNOWN`
   - plus a short note describing what was assumed.

