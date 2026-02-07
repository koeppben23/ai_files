# Backend Java Profile Rulebook (v2.1)
Backend Java Profile Rulebook (v2.1)

This document defines **backend Java (Spring Boot)** profile rules.
It is applied **in addition** to the Core Rulebook (`rules.md`) and the Master Prompt (`master.md`).

**Intent:** enforce *provable* best-practice engineering defaults so the system reliably produces  
**top-tier business code and tests** — not by intention, but by **verified evidence**.

Priority order on conflict:
`master.md` > `rules.md` (Core) > this profile.

---
# Templates Addon (Binding)

For the `backend-java` profile, deterministic generation requires the templates addon:
`rules.backend-java-templates.md`.

Binding:
- At **code-phase** (Phase 4+), the workflow MUST load the templates addon and record it in:
  - `SESSION_STATE.LoadedRulebooks.templates`
- When loaded, templates are binding defaults; if a template conflicts with locked repo conventions, apply the minimal convention-aligned adaptation and document the deviation.

---

# Kafka Templates Addon (Binding)

For the `backend-java` profile, Kafka-related code and tests MUST follow the Kafka templates addon:
`rules.backend-java-kafka-templates.md`.

Activation (binding):
- At **code-phase** (Phase 4+), the workflow MUST load this addon and record it in:
  - `SESSION_STATE.LoadedRulebooks.addons.kafka`
- The addon is REQUIRED if ANY of the following is true (evidence-based):
  - Repo Discovery finds Kafka usage signals (e.g., `@KafkaListener`, `spring-kafka` dependency, or `spring.kafka` config keys), OR
  - The ticket/request explicitly requires Kafka producer/consumer changes.

If required but missing at code-phase:
- The workflow MUST record:
  - `SESSION_STATE.AddonsEvidence.kafka.status = missing-rulebook`
  - `SESSION_STATE.LoadedRulebooks.addons.kafka = ""`
- The assistant MUST explicitly warn that Kafka-related changes cannot be produced safely without the addon rulebook,
  and MUST limit output to analysis/planning until the operator provides or adds the addon rulebook.

Addon policy classes (binding):
- **Required addons** (code-generation-critical): may hard-block in code-phase if missing.
- **Advisory addons** (quality amplifiers): should emit WARN status + recovery steps and continue conservatively.
- Addon manifests/rulebooks MUST explicitly declare which class they belong to.

---
## 0. Core Principle (Binding, Non-Negotiable)

> **No claim without evidence. No evidence, no acceptance.**

Any statement such as:
- “tests are green”
- “contract matches”
- “no architecture violations”
- “coverage is sufficient”
- “static analysis is clean”

is **invalid** unless supported by **BuildEvidence** captured in `SESSION_STATE`.

If evidence is missing, the system must explicitly state:
> *“Not verified – evidence missing.”*

---

## 1. Key Outcomes (Binding)

A backend Java change is considered **DONE** only if all outcomes below are **verified**:

1) **Contract fidelity** – API/event behavior matches the authoritative contract  
2) **Architecture hygiene** – no layer/module boundary violations  
3) **High-signal tests** – deterministic, behavior-focused, relevant  
4) **Operational readiness** – logging, metrics, tracing, security preserved or improved  
5) **Reproducibility** – generated artifacts are never hand-edited  
6) **Evidence-backed** – all quality claims supported by BuildEvidence

---

## 2. Technology Stack Defaults (Repo-First)

Unless repository evidence says otherwise, assume:

- Java 21
- Spring Boot 3.x
- Maven (Gradle only if repo uses it)
- JPA/Hibernate (if present)
- Liquibase/Flyway (repo-driven)
- OpenAPI Generator (contract-first if specs exist)
- MapStruct / Lombok (if present)
- Actuator + Micrometer + OpenTelemetry (if present)
- Spring Security (if present)
- Kafka (if present)

**Binding rule:**  
If a tool exists in the repo, it is **not optional**. Its results are gating.

## 2.1 Repo Conventions Lock (Binding)
Before producing code, the system MUST explicitly detect and record (in SESSION_STATE) the repo’s concrete conventions:
- Build tool + module selection strategy (mvnw/gradlew, multi-module flags)
- Web stack (Spring MVC vs WebFlux), serialization (Jackson settings if discoverable)
- Error contract (problem+json / custom envelope / codes) and mapping location
- Validation approach (jakarta validation + @Validated usage, custom validators)
- Test stack (JUnit5/JUnit4, AssertJ/Hamcrest, Mockito, Testcontainers, WireMock, RestAssured, etc.)
- Formatting/lint gates (Spotless/Checkstyle/PMD/SpotBugs/ErrorProne/Sonar)

Rule: once detected, these conventions become constraints for the task.
If not detectable, the assistant MUST mark the convention as "unknown" and avoid introducing new patterns.

---

## 3. Code Style & Determinism (Binding)

### 3.1 Style
- Follow repo style; default to Google Java Style if ambiguous
- No wildcard imports
- No production `TODO` / `FIXME` without explicit approval

### 3.2 Nullability
- Non-null by default
- `Optional` only for return values

### 3.3 Time & Randomness
- Inject `Clock`
- Seed randomness in tests
- No sleeps; use Awaitility if async

### 3.4 Dependency Injection & Immutability (Binding)
- Constructor injection only (no field injection)
- Prefer immutable objects: `final` fields, no setter-based mutation unless repo pattern requires it
- DTOs: prefer `record` if repo already uses records; otherwise follow repo DTO pattern
- Lombok (if present): avoid `@Data` on domain/entities; prefer explicit methods or focused Lombok annotations
- No `Optional` as parameter/field; `Optional` only for return values (already stated) and enforce it strictly

### 3.5 Forbidden Patterns (Binding)
The following are NOT allowed in generated production code unless the repo already uses them and it is consistent:
- Business branching inside controllers/adapters
- Returning JPA entities from controllers
- Catching `Exception` / swallowing exceptions / logging-only error handling
- Introducing new framework patterns (e.g., reactive stack) without repo evidence
- Commented-out code or TODO/FIXME in production without explicit approval

---

## 4. Architecture Rules (Enforced)

### 4.1 Architecture Detection (Binding)
Detect and **lock** the repo’s architecture pattern:
- Feature-modular layered
- Classic layered
- Hexagonal (ports & adapters)

**Rule:** Once detected, do not mix patterns within a change.

### 4.2 Controllers / Boundaries (Binding)
Controllers or API adapters must:
- validate input
- map DTOs
- delegate
- handle HTTP concerns

**Forbidden:**
- business branching
- persistence logic
- transaction management

### 4.3 Services & Use Cases (Binding)
- Services represent **use cases**, not entities
- No god services
- Domain invariants enforced in business logic

### 4.4 Transactions (Binding)
- One transaction per use case
- No external calls inside DB transactions unless compensated
- Idempotency required for external triggers

### 4.5 Messaging (Binding if present)
- Consumers must be idempotent
- Retries bounded and observable
- Contract-driven event schemas respected

### 4.6 Persistence Hygiene (Binding if JPA present)
- Prevent lazy-loading leaks across boundary: controllers must not trigger lazy graph loading
- Avoid N+1: prefer fetch joins/entity graphs where repo conventionally does
- Use `@Transactional(readOnly = true)` for read use cases when appropriate
- Consider optimistic locking (`@Version`) for aggregate updates with concurrent writers
- Map persistence models to boundary DTOs explicitly (no entity exposure)

---

## 5. Contracts & Code Generation (Binding)

### 5.1 Contract Authority
If OpenAPI/Pact exists:
- Contract is authoritative
- Code adapts to contract, never the other way around

### 5.2 OpenAPI Codegen Policy (Binding)
**NEVER**
- Edit generated code
- Place business logic in generated packages

**MUST**
- Treat generated code as boundary
- Map DTOs explicitly (adapter layer)
- Keep generation reproducible

**Submodule rule (binding):**
If APIs live in a separate `apis` submodule:
- Spec changes occur in `apis` first
- Backend updates only via submodule reference bump
- Regenerated sources + tests are mandatory

### 5.3 Contract Drift Gate (Binding)
If drift detection exists:
- Drift → **hard failure**
- No bypass without documented exception

---

## 6. Error Handling (Binding)

- Centralized error mapping (`@ControllerAdvice`)
- Stable error codes
- No internal leakage
- Prefer RFC7807 if repo uses it

### 6.1 Error Contract Tests (Binding)
For any changed public endpoint behavior:
- Assert HTTP status + stable error code (and optionally correlationId propagation if part of contract)
- Do NOT assert full error messages unless the repo treats messages as contract

---

## 7. Testing Rules (Top-Tier)

### 7.1 Test Pyramid (Binding)
1) Unit (business logic, no Spring)
2) Slice (web/persistence)
3) Integration (only if risk requires)
4) E2E/BDD only if established

### 7.2 Behavioral Coverage Matrix (Binding)
For changed public behavior, consider:
- HAPPY_PATH
- VALIDATION
- NOT_FOUND / EMPTY
- STATE_INVALID
- AUTHORIZATION
- BOUNDARIES
- DB CONSTRAINTS
- ASYNC (if applicable)

### 7.3 Test Quality Rules (Binding)
- Deterministic
- Behavior-focused
- No overspecification
- No flakiness

Additional determinism requirements (binding):
- If time is involved, use an injectable `Clock` (or the repo’s existing time abstraction); tests MUST use a fixed clock.
- Avoid randomly generated identifiers in assertions; use fixed IDs or an injectable ID generator if present.
- Avoid order-dependent assertions unless order is part of the contract; otherwise sort deterministically.
- Prefer high-signal assertions (domain outcome, error contract) over snapshot-style full JSON/body comparisons,
  unless the repo already uses contract snapshots for that boundary.

### 7.3.1 Test Design Contract (Binding)
- Use Given/When/Then (or Arrange/Act/Assert) consistently
- Prefer asserting outputs/state transitions over verifying internal interactions
- Use parameterized tests for boundary sets (validation ranges, edge cases)
- Use test data builders/object mothers to keep tests readable and reduce duplication
- Each extracted business rule must map to at least one named test that proves it

Templates (binding when loaded):
- If `rules.backend-java-templates.md` is loaded, its patterns for builders and test classes MUST be followed.

### 7.4 Architecture Tests (Binding if ArchUnit present)
- New boundaries → new ArchUnit rules
- Violations → hard failure

### 7.5 Contract Tests (Binding if contracts exist)
- Endpoint behavior
- Error mapping
- Security semantics
- No volatile assertions

### 7.6 Advanced Test Excellence (Binding when applicable)
- Mutation testing (if tooling exists, e.g., PIT): changed business logic SHOULD maintain a non-regressing mutation score; if score drops materially, record risk and remediation.
- Property/invariant tests (if generators exist): for non-trivial domain calculations/transformations, add at least one property-style test.
- Concurrency tests: for changes touching locking/versioning/retries/idempotency, include at least one deterministic concurrent scenario.
- Contract-negative tests: for API changes, include at least one malformed/invalid request test proving stable error contract.

---

## 8. Database & Migrations (Binding)

- Migrations only (no manual DB changes)
- Constraints require tests (happy + violation)
- Risky migrations require operational note

---

## 9. Observability & Operations (Binding)

- Correlation IDs propagated
- Logs structured and safe
- Metrics/traces preserved or extended
- No secrets or raw PII in logs

---

## 10. Security-by-Default (Binding)

- Explicit authorization on external endpoints
- Input validation mandatory
- Dependency security gates must remain green

---

## 11. Quality Gates (Hard Fail)

A change **fails** if any is true:

### QG-1 Build Gate
- Build not green
- Static analysis regressions

### QG-2 Contract Gate
- Contract drift
- Edited generated code
- Missing regeneration

### QG-3 Architecture Gate
- Layer/module violations
- Fat controllers

### QG-4 Test Quality Gate
- Missing behavioral coverage
- Flaky or low-signal tests
- Missing required determinism seams for changed logic (time/random/order)
- Missing concurrency/idempotency evidence where applicable

### QG-5 Operational Gate
- Logging/metrics/tracing/security regression

---

## 12. BuildEvidence Gate (The Critical Enforcer) (Binding)

### 12.1 Definition
**BuildEvidence** is concrete proof captured in `SESSION_STATE`, consisting of:
- command executed
- tool name
- relevant output snippet (pass/fail summary)

### 12.2 Mandatory Evidence for Claims
The following claims are **forbidden** without evidence:

| Claim | Required Evidence |
|-----|------------------|
| “Tests are green” | test command + summary |
| “Coverage is sufficient” | coverage report snippet |
| “No contract drift” | OpenAPI/Pact validation output |
| “Architecture is clean” | ArchUnit output |
| “Static analysis is clean” | tool summary |

### 12.2.1 Minimal Evidence by Change Type (Binding)
The assistant MUST request/expect evidence appropriate to the change:
- API/Controller change: tests covering HTTP contract + error contract + security semantics (if security present)
- Persistence/migration change: migration validation + happy + violation tests for constraints
- Messaging change: consumer idempotency/retry behavior tests (as applicable) + schema validation (if exists)
- Pure service change: unit tests proving rules + relevant slice/integration only if boundary behavior changed

### 12.3 Enforcement Rule
If evidence is missing:
- the system must say **“not verified”**
- the change cannot pass Phase 5.5 / 6

No exceptions.

---

## 13. Final Definition of Done (Binding)

A backend Java change is **DONE** only if:

- All Quality Gates pass
- All claims are evidence-backed
- No generated code was edited
- Architecture boundaries are intact
- Tests prove behavior, not implementation
- Operational readiness is preserved
- SESSION_STATE contains BuildEvidence

If any item is missing → **NOT DONE**.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

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

## Java-first Principal Hardening v2 (Binding)

This section defines Java-specific, measurable hardening rules for business and test code.

### JPH2-1 Risk tiering by touched surface (binding)

The workflow MUST classify changed scope before implementation and gate reviews:

- `TIER-LOW`: internal refactor without contract/persistence/async changes
- `TIER-MEDIUM`: service/business logic or controller behavior change
- `TIER-HIGH`: persistence/migration, security semantics, async messaging, or externally visible contract change

If classification is uncertain, default to the higher tier.

### JPH2-2 Mandatory evidence pack per tier (binding)

`TIER-LOW` requires evidence for:
- build
- changed-module tests

`TIER-MEDIUM` requires evidence for:
- build
- changed-module tests
- at least one negative-path test for changed behavior

`TIER-HIGH` requires evidence for:
- build
- changed-module tests
- contract or schema checks (if repo tooling exists)
- one deterministic negative-path test and one deterministic resilience test (retry/idempotency/concurrency as applicable)

### JPH2-3 Hard fail criteria for principal acceptance (binding)

A Java change MUST be marked `fail` in P5.3/P6 if any applies:

- `JPH2-FAIL-01`: no evidenceRef for a critical claim
- `JPH2-FAIL-02`: contract-facing change without negative-path proof
- `JPH2-FAIL-03`: async/persistence risk change without deterministic resilience proof
- `JPH2-FAIL-04`: generated code modified by hand
- `JPH2-FAIL-05`: flaky test behavior detected (fixed sleeps or nondeterministic timing)

### JPH2-4 Required test matrix mapping (binding)

For changed behavior, at least the following matrix entries MUST be represented:

- API/controller changes -> happy path + validation/error path
- business-rule changes -> rule happy path + rule violation path
- persistence changes -> constraint happy path + constraint violation path
- async messaging changes -> consume/publish happy path + duplicate/retry/idempotency path

If a row is not applicable, record explicit rationale in evidence.

### JPH2-5 Determinism and flakiness budget (binding)

- `Thread.sleep` in new/changed tests is forbidden when Awaitility or equivalent exists.
- New/changed tests MUST control time via injected seam (`Clock` or repo equivalent).
- New/changed assertions MUST avoid order dependence unless order is contractually required.

If any of the above is violated, status MUST include `WARN-JAVA-DETERMINISM-RISK` and gate result cannot be `pass`.

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
