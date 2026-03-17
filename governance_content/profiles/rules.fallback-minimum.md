# Fallback Minimum Profile Rulebook (v1.0)

## Intent (binding)

Provide a mandatory baseline when a target repository lacks explicit standards (no CI, no test conventions, no documented build steps).

## Scope (binding)

Applies to repos where no deterministic stack profile can be selected and minimum safe build/test/docs governance is required.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This fallback profile applies only when no stack profile can be selected deterministically.
It is applied in addition to `master.md` (phases, gates, activation) and `rules.md` (core engineering governance).

## Activation condition
This profile applies ONLY when no repo-local standards are discoverable.

## Phase integration (binding)

- Phase 2: document missing standards and the minimum runnable baseline proposal.
- Phase 2.1: include explicit decision for minimal verification path (unit/integration/smoke).
- Phase 4: implement the smallest safe baseline for build/test/docs in changed scope.
- Phase 5/6: verify executed evidence or mark `not-verified` with copy/paste recovery commands.

## Evidence contract (binding)

When fallback is active, maintain:
- `SESSION_STATE.BuildEvidence` entries for every verification claim.
- `SESSION_STATE.RiskTiering` rationale or explicit fallback rationale when canonical tiering data is unavailable.
- `warnings[]` with recovery actions when checks cannot be executed in the current environment.

If evidence is missing, claims MUST be marked `not-verified` and completion MUST remain non-final.

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

## Minimal tooling commands (recommended)

Use repo-native commands when available; otherwise propose minimal equivalents:
- Python: `${PYTHON_COMMAND} -m pytest -q`
- Node: `npm test`
- Maven: `mvn -q test`
- Gradle: `./gradlew test`
- Build smoke: repo-native build command + one startup/check command

## Documentation (MUST)
- Ensure build/test instructions exist (create minimal documentation if missing).
- Record non-trivial decisions in ADR.md or an equivalent mechanism.

## Quality heuristics (SHOULD)
- Deterministic behavior; no hidden mutable state.
- Coherent error handling; no silent failures.
- Logging at critical boundaries without leaking sensitive data.

## Naming Conventions (SHOULD)

When no repo conventions are discoverable, apply these minimal defaults:

**Files:**
- Source files: `snake_case` (Python), `PascalCase` (Java/C#), `kebab-case` (TypeScript/JavaScript)
- Test files: mirror source file name with `test_` prefix (Python) or `.spec.`/`.test.` suffix (JS/TS) or `Test` suffix (Java)

**Classes and functions:**
- Classes: `PascalCase` (all languages)
- Functions/methods: `snake_case` (Python), `camelCase` (Java/TS/JS)
- Constants: `UPPER_SNAKE_CASE`
- Private members: language-idiomatic convention (`_prefix` for Python, `private` for Java/TS)

**Test naming:**
- Test functions/methods: describe behavior, not implementation
- Pattern: `test_{what}_{condition}_{expected}` (Python) or `{method}_{condition}_{expected}` (Java) or `it('should {behavior}', ...)` (JS/TS)

**General rules:**
- Names SHOULD convey intent and domain meaning (not abbreviations or single letters).
- Names MUST NOT shadow built-in language constructs.
- Names SHOULD be consistent within the codebase: if a convention exists, follow it; if not, establish one and follow it consistently.

## Portability (MUST when persisting)
Use platform-neutral storage locations as defined in rules.md.

---

## Decision Trees (Binding)

When no specialized profile matches, use these minimal decision trees to guide implementation decisions.

### DT-FM1: Architecture Pattern Detection

When working with an unfamiliar codebase:

```
START -> Can you identify the existing architecture pattern from the code structure?
  YES -> Follow detected pattern. Document it in SESSION_STATE. STOP.
         Examples of detectable patterns:
         - Layered: controllers/handlers -> services -> repositories/DAOs
         - MVC: models + views/templates + controllers
         - Event-driven: producers/publishers + consumers/handlers + event schemas
         - Monolith: single deployable with internal modules
  NO  -> Is the codebase small (<20 source files)?
    YES -> Flat structure is acceptable. Group by function (src/, tests/, config/).
    NO  -> Create feature-based grouping:
           {feature}/models, {feature}/logic, {feature}/tests
           Reason: Cohesion by feature works across all languages.
```

### DT-FM2: Test Strategy Selection

When deciding what to test:

```
START -> Does the codebase have existing tests?
  YES -> Follow existing test conventions:
         - Use the same test framework
         - Mirror existing test file naming and location
         - Follow existing assertion style
         THEN select test types below.
  NO  -> Add minimal test infrastructure:
         - Identify the language-standard test runner
         - Create test directory mirroring source structure
         - Add at least one smoke test proving the build works
         THEN select test types below.

For each changed component:
|
+-- Business logic (calculations, rules, validations)
|   -> Unit test: test inputs -> outputs with no external dependencies
|   -> Must include: happy path + at least one error/edge case
|
+-- Data access (database, file I/O, external API calls)
|   -> Integration test: test with real or in-memory data store
|   -> If not feasible: unit test with mocked I/O + document limitation
|
+-- API / Entry point (HTTP, CLI, message handler)
|   -> Integration test: test request -> response mapping
|   -> Include: success path + at least one error path (400/404/500)
|
+-- Configuration / Wiring
   -> Smoke test: verify the application starts successfully
```

### DT-FM3: Technology Decision (Generic)

When a new library or tool is needed in an unfamiliar codebase:

```
START -> Is the capability already present in the codebase's dependencies?
  YES -> Use existing dependency. STOP.
  NO  -> Is there a standard library solution in the language?
    YES -> Use standard library. STOP.
    NO  -> Check the language ecosystem for the most widely-used solution:
           - Document the choice and rationale in the plan
           - Pin the version
           - Prefer libraries with active maintenance (recent commits, issue responses)
           - Avoid libraries that pull large transitive dependency trees
```

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

## Examples (GOOD/BAD)

GOOD:
- Unknown repo receives a minimal deterministic verification plan (build + targeted test or smoke check) with explicit evidence capture.

BAD:
- Declaring completion without any executable verification or recovery guidance.

---

## Anti-Patterns Catalog (Binding)

Even in fallback/unknown repos, these universal anti-patterns MUST be avoided. Each includes an explanation of **why** it is harmful.

### AP-FM01: Silent Error Swallowing

**Pattern:** `try/except: pass`, `catch (Exception e) { }`, or `.catch(() => {})` with no logging, rethrow, or recovery.

**Why it is harmful:**
- Errors become invisible: the system continues in an undefined state.
- Debugging becomes impossible: there is no trace of what went wrong.
- Data corruption can occur silently without any alert.

---

### AP-FM02: Untested Changes Declared Complete

**Pattern:** Marking a change as "done" or "ready-for-pr" without any form of verification evidence (test, lint, smoke, build).

**Why it is harmful:**
- No safety net: bugs are discovered by users in production instead of by automated checks.
- Quality claims are unsubstantiated: "it works" without evidence is not a professional statement.
- Violates the core governance principle: no claim without evidence.

---

### AP-FM03: Hardcoded Secrets or Credentials

**Pattern:** API keys, passwords, tokens, or connection strings embedded directly in source code, tests, or configuration files.

**Why it is harmful:**
- Secrets committed to version control are visible to everyone with repo access (and potentially the internet).
- Rotating compromised credentials requires finding and updating all hardcoded instances.
- Test secrets may inadvertently connect to production systems.

---

### AP-FM04: Nondeterministic Test Dependencies

**Pattern:** Tests that depend on current time, random values, network availability, or execution order without explicit control.

**Why it is harmful:**
- Tests that pass locally may fail in CI (or vice versa), eroding trust in the test suite.
- Intermittent failures waste developer time investigating "phantom" bugs.
- Order-dependent tests mask coupling issues in the codebase.

---

### AP-FM05: No Rollback Strategy for Non-Trivial Changes

**Pattern:** Deploying schema changes, data migrations, or breaking API changes without a documented rollback plan.

**Why it is harmful:**
- If the deployment fails, there is no way to recover: the system stays broken.
- Incomplete migrations can leave databases in inconsistent states.
- Downstream consumers may break with no way to revert to the previous behavior.

---

## Troubleshooting

1) Symptom: No runnable test tool is available
- Cause: repo has no test harness or missing dependencies in host
- Fix: document `not-verified`, provide minimal bootstrap command, and run smoke validation.

2) Symptom: Build command unclear in legacy repository
- Cause: missing docs/CI conventions
- Fix: infer from repo files, record assumption, and provide conservative fallback commands.

3) Symptom: Gate cannot pass due missing evidence
- Cause: claims made without BuildEvidence links
- Fix: execute minimal checks and map each claim to explicit evidence refs.

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

# End of file — rules.fallback-minimum.md
