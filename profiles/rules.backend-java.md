# Backend Java Profile Rulebook (v2.2)

This document defines **backend Java (Spring Boot)** profile rules.
It is applied **in addition** to the Core Rulebook (`rules.md`) and the Master Prompt (`master.md`).

## Intent (binding)

Enforce provable best-practice engineering defaults so the system reliably produces top-tier business code and tests by verified evidence.

## Scope (binding)

Backend-java business logic, architecture boundaries, contract alignment, deterministic tests, and backend operational quality gates.

## Activation (binding)

This profile applies when backend-java stack evidence is selected by governance profile detection (explicit user choice or deterministic discovery).

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
For backend-java behavior, this profile governs stack-specific rules and activated addons/templates may refine within profile constraints.

## Phase integration (binding)

- Phase 2: discover stack/tooling conventions and addon requirements.
- Phase 4: apply profile + required templates/addons for implementation planning/execution.
- Phase 5/6: verify evidence-backed architecture/test/business/rollback quality gates.

## Evidence contract (binding)

- Every non-trivial quality claim MUST map to BuildEvidence.
- Missing evidence MUST be reported as `not-verified` and cannot support gate pass claims.

## Tooling (binding)

- Use repo-native Java commands (Maven/Gradle/tests/lint/static analysis) when available.
- Non-runnable tooling in current host MUST be reported with recovery commands and `not-verified` claims.

---
# Templates Addon (Binding)

For the `backend-java` profile, deterministic generation requires the templates addon:
`rules.backend-java-templates.md`.

Binding:
- At **code-phase** (Phase 4+), the workflow MUST load the templates addon and record it in:
  - `SESSION_STATE.LoadedRulebooks.templates`
- The load evidence MUST include resolved path plus version/digest evidence when available:
  - `SESSION_STATE.RulebookLoadEvidence.templates`
- When loaded, templates are binding defaults; if a template conflicts with locked repo conventions, apply the minimal convention-aligned adaptation and document the deviation.

---

# Kafka Templates Addon (Binding)

For the `backend-java` profile, Kafka-related code and tests MUST follow the Kafka templates addon:
`rules.backend-java-kafka-templates.md`.

Activation (binding):
- In **Phase 1/2**, the workflow MUST evaluate whether Kafka addon is required and record evidence in:
  - `SESSION_STATE.AddonsEvidence.kafka.required = true | false`
  - `SESSION_STATE.AddonsEvidence.kafka.evidence = <short evidence-based rationale>`
- Kafka addon is REQUIRED if ANY of the following is true (evidence-based):
  - Repo Discovery finds Kafka usage signals (e.g., `@KafkaListener`, `spring-kafka` dependency, or `spring.kafka` config keys), OR
  - The ticket/request explicitly requires Kafka producer/consumer changes.
- In **code-phase** (Phase 4+), load and record this addon ONLY when `required = true`:
  - `SESSION_STATE.LoadedRulebooks.addons.kafka = rules.backend-java-kafka-templates.md`
- If `required = false`, keep:
  - `SESSION_STATE.LoadedRulebooks.addons.kafka = ""`

If `required = true` but addon rulebook is missing at code-phase:
- The workflow MUST record:
  - `SESSION_STATE.AddonsEvidence.kafka.status = missing-rulebook`
  - `SESSION_STATE.LoadedRulebooks.addons.kafka = ""`
- The workflow MUST explicitly warn that Kafka-related changes cannot be produced safely without the addon rulebook.
- The workflow MUST restrict output to analysis/planning + recovery steps and MUST NOT generate unsafe Kafka code/tests.
- In fail-closed code-phase handling, apply canonical required-addon policy from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` / `master.md`
  (this profile references but does not redefine that policy).

Addon policy classes (binding):
- Addon class semantics are canonical in `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`; this profile MUST reference, not redefine, those semantics.
- Addon manifests/rulebooks MUST explicitly declare class (`required` | `advisory`).
- This profile may define backend-java-specific required-signal logic, but missing-rulebook handling MUST follow canonical policy.

---

## Shared Principal Governance Contracts (Binding)

To keep this profile focused on Java-specific engineering behavior, shared principal governance contracts are modularized into advisory rulebooks:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior for `backend-java` profile:

- At code/review phases (Phase 4+), these shared contracts MUST be loaded as advisory governance contracts.
- When loaded, record in:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- If one of these shared rulebooks is unavailable, the workflow MUST emit a warning, mark affected claims as
  `not-verified`, and continue conservatively without inventing evidence.

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

If evidence is missing, the system MUST explicitly state:
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
- If a tool exists in the repo **and is runnable in the current environment**, it is not optional; execute it and capture evidence.
- If a tool exists but is not runnable in the current environment, mark claims as `not-verified`, emit recovery commands,
  and continue conservatively without fabricating gate success.

## 2.1 Repo Conventions Lock (Binding)
Before producing code, the system MUST explicitly detect and record (in SESSION_STATE) the repo’s concrete conventions:
- Build tool + module selection strategy (mvnw/gradlew, multi-module flags)
- Web stack (Spring MVC vs WebFlux), serialization (Jackson settings if discoverable)
- Error contract (problem+json / custom envelope / codes) and mapping location
- Validation approach (jakarta validation + @Validated usage, custom validators)
- Test stack (JUnit5/JUnit4, AssertJ/Hamcrest, Mockito, Testcontainers, WireMock, RestAssured, etc.)
- Formatting/lint gates (Spotless/Checkstyle/PMD/SpotBugs/ErrorProne/Sonar)

Rule: once detected, these conventions become constraints for the task.
If not detectable, the workflow MUST mark the convention as "unknown" and avoid introducing new patterns.

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
- SHOULD use immutable objects: `final` fields, no setter-based mutation unless repo pattern requires it
- DTOs: prefer `record` if repo already uses records; otherwise follow repo DTO pattern
- Lombok (if present): SHOULD NOT use `@Data` on domain/entities; SHOULD use explicit methods or focused Lombok annotations
- No `Optional` as parameter/field; `Optional` only for return values (already stated) and enforce it strictly

### 3.5 Forbidden Patterns (Binding)
The following are NOT allowed in generated production code unless the repo already uses them and it is consistent:
- Business branching inside controllers/adapters
- Returning JPA entities from controllers
- Catching `Exception` / swallowing exceptions / logging-only error handling
- Introducing new framework patterns (e.g., reactive stack) without repo evidence
- Commented-out code or TODO/FIXME in production without explicit approval

### 3.6 Naming Conventions (Binding)

The following naming conventions are binding unless repo conventions explicitly differ (in which case, follow repo conventions and record deviation).

**Classes:**

| Type | Convention | Example |
|------|-----------|---------|
| Controller | `{Resource}Controller` | `UserController`, `OrderController` |
| Service (use case) | `{Resource}Service` | `UserService`, `OrderService` |
| Repository | `{Resource}Repository` | `UserRepository`, `OrderRepository` |
| Entity | `{Resource}` (singular, PascalCase) | `User`, `Order`, `Product` |
| DTO (request) | `{Resource}CreateRequest`, `{Resource}UpdateRequest` | `UserCreateRequest` |
| DTO (response) | `{Resource}Response` | `UserResponse`, `OrderResponse` |
| Mapper | `{Resource}Mapper` | `UserMapper`, `OrderMapper` |
| Exception | `{Resource}NotFoundException`, `{Domain}Exception` | `UserNotFoundException` |
| Config | `{Feature}Config`, `{Feature}Properties` | `SecurityConfig`, `CacheProperties` |

**Methods:**

| Type | Convention | Example |
|------|-----------|---------|
| Service create | `create({Resource})` | `create(user)` |
| Service find | `findById(id)`, `findAll(...)` | `findById(1L)` |
| Service update | `update(id, {Resource})` | `update(1L, user)` |
| Service delete | `delete(id)` | `delete(1L)` |
| Entity validation | `validate()`, `validateCanBe{Action}()` | `validateCanBeDeleted()` |
| Entity state change | `{action}(params)` | `activate()`, `deactivate()` |
| Mapper to-domain | `toDomain(request)` | `toDomain(createRequest)` |
| Mapper to-response | `toResponse({resource})` | `toResponse(user)` |

**Test classes and methods:**

| Type | Convention | Example |
|------|-----------|---------|
| Test class | `{ClassUnderTest}Test` | `UserServiceTest`, `UserControllerTest` |
| Test method | `{method}_{condition}_{expected}` | `create_withValidInput_persistsUser()` |
| Test display name | Natural language with `@DisplayName` | `"should persist user with timestamps"` |
| Test data builder | `{Resource}TestDataBuilder` | `UserTestDataBuilder` |
| Builder method | `given{Resource}()` | `givenUser()` |
| Nested test class | Method name (PascalCase) | `class Create { }`, `class FindById { }` |

**Packages:**

| Type | Convention | Example |
|------|-----------|---------|
| Feature root | `com.company.{app}.{feature}` | `com.acme.shop.order` |
| Controller layer | `{feature}.api` or `{feature}.controller` | `order.api` |
| Service layer | `{feature}.service` or `{feature}.application` | `order.service` |
| Domain layer | `{feature}.domain` or `{feature}.model` | `order.domain` |
| Repository layer | `{feature}.repository` or `{feature}.persistence` | `order.repository` |
| Config | `{feature}.config` | `order.config` |
| Exception | `{feature}.exception` | `order.exception` |
| Mapper | `{feature}.mapper` | `order.mapper` |

---

## 4. Architecture Rules (Enforced)

### 4.1 Architecture Detection (Binding)
Detect and **lock** the repo's architecture pattern:
- Feature-modular layered
- Classic layered
- Hexagonal (ports & adapters)

**Rule:** Once detected, do not mix patterns within a change.

### 4.1a Architecture Pattern Selection Decision Tree (Binding)

When creating a new module or service from scratch (no existing pattern to follow), use this decision tree:

```
START -> Does the repo already have an established architecture pattern?
  YES -> Follow detected pattern (4.1 Architecture Detection). STOP.
  NO  -> Is the service primarily API-driven with external consumers?
    YES -> Does it require complex domain logic (>3 business rules, aggregates)?
      YES -> Hexagonal (ports & adapters)
             Reason: Isolates domain from infrastructure; testable without frameworks.
      NO  -> Classic layered (Controller -> Service -> Repository)
             Reason: Simplicity; sufficient for delegation-only services.
    NO  -> Is it an event-driven or messaging-focused service?
      YES -> Hexagonal (ports & adapters)
             Reason: Ports for each messaging channel enable independent testing.
      NO  -> Feature-modular layered
             Reason: Organize by feature (not layer) for cohesion in multi-feature services.
```

Record decision in `SESSION_STATE.ArchitectureDecisions` with evidence path.

### 4.1b Test Type Selection Decision Tree (Binding)

For each changed component, select the appropriate test types:

```
START -> What type of component changed?
|
+-- Controller / API endpoint
|   -> Slice test (@WebMvcTest): HTTP mapping, status codes, serialization, error responses
|   -> Unit test: only if input validation logic is extracted to a separate class
|   -> Contract test: only if external consumers exist (Phase 3 evidence required)
|
+-- Service / Use case
|   -> Unit test: business logic with mocked dependencies (Mockito)
|   -> Do NOT use @SpringBootTest for services -- no Spring context needed
|   -> Integration test: only if orchestrating multiple repos with @Transactional
|
+-- Repository / Persistence
|   -> Slice test (@DataJpaTest): queries, constraints, mappings
|   -> Must include: happy path + constraint violation + empty result
|   -> Never mock the database -- use the slice test's embedded DB
|
+-- Domain entity / Value object
|   -> Unit test: invariants, business methods, equality contract
|   -> No mocking -- entities must be testable in isolation
|   -> Include: valid construction, invalid construction (rejected), state transitions
|
+-- Configuration / Infrastructure
|   -> Integration test: verify wiring works end-to-end
|   -> Include: startup smoke test if new beans/configurations are added
|
+-- Cross-cutting (security, logging, interceptors)
   -> Slice test: @WithMockUser + @WebMvcTest for security
   -> Unit test: for utility/helper classes
```

Record selected test types in plan's Test Strategy section.

### 4.1c Technology Decision Tree (Binding)

When a new library or framework component is needed:

```
START -> Is the capability already provided by an existing dependency?
  YES -> Use existing dependency. Do NOT add alternatives. STOP.
  NO  -> Is the capability provided by the Spring ecosystem?
    YES -> Use the Spring module (Spring Security, Spring Data, Spring Cache, etc.).
           Reason: Consistent configuration, tested integration, same lifecycle.
    NO  -> Is this a build/dev dependency or a runtime dependency?
      BUILD -> Follow repo convention (Maven plugin preferred if available).
      RUNTIME -> Is there precedent in the repo's dependency tree?
        YES -> Use the same library family/version.
        NO  -> Prefer well-maintained, minimal-transitive-dependency libraries.
               Document the choice in the plan's Architecture Options.
               Add version to BOM/dependency management if one exists.
```

### 4.1d Module and Package Creation Decision Tree (Binding)

When new packages or modules are needed:

```
START -> Does the feature belong to an existing domain module?
  YES -> Add within existing module's package structure. STOP.
         Follow established sub-package convention (controller/service/domain/repository).
  NO  -> Does the feature represent a new bounded context?
    YES -> Create new top-level module:
           Package: {base}.{feature}
           Sub-packages: per detected architecture pattern (4.1)
           Required: package-info.java documenting module purpose
           Required: module-level README or ADR entry
    NO  -> Is it a cross-cutting utility (logging, security, common helpers)?
      YES -> Add to existing shared/common module.
             If no shared module exists: create {base}.common.{concern}
      NO  -> Add to the module closest to the primary consumer.
             If equally close to multiple modules: create shared module.
```

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
- SHOULD NOT use N+1 queries: SHOULD use fetch joins/entity graphs where repo conventionally does
- Use `@Transactional(readOnly = true)` for read use cases when appropriate
- SHOULD use optimistic locking (`@Version`) for aggregate updates with concurrent writers
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
- SHOULD use RFC7807 if repo uses it

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
For changed public behavior, the coverage matrix SHOULD include:
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
- MUST NOT use randomly generated identifiers in assertions; use fixed IDs or an injectable ID generator if present.
- MUST NOT use order-dependent assertions unless order is part of the contract; otherwise sort deterministically.
- SHOULD use high-signal assertions (domain outcome, error contract) over snapshot-style full JSON/body comparisons,
  unless the repo already uses contract snapshots for that boundary.

### 7.3.1 Test Design Contract (Binding)
- Use Given/When/Then (or Arrange/Act/Assert) consistently
- SHOULD assert outputs/state transitions over verifying internal interactions
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
- Mutation testing (if tooling exists, e.g., PIT): changed business logic SHOULD maintain a non-regressing mutation score; if score drops by more than 5% (absolute) from the pre-change baseline, record risk and remediation plan.
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
The workflow MUST request/expect evidence appropriate to the change:
- API/Controller change: tests covering HTTP contract + error contract + security semantics (if security present)
- Persistence/migration change: migration validation + happy + violation tests for constraints
- Messaging change: consumer idempotency/retry behavior tests (as applicable) + schema validation (if exists)
- Pure service change: unit tests proving rules + relevant slice/integration only if boundary behavior changed

### 12.3 Enforcement Rule
If evidence is missing:
- the system MUST say **“not verified”**
- the change cannot pass Phase 5.3 / 6

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

Shared contract note:
- Principal scorecard/claim-to-evidence/exit-calibration rules are defined in:
  - `rules.principal-excellence.md`
  - `rules.risk-tiering.md`
  - `rules.scorecard-calibration.md`
and apply as advisory governance contracts for this profile.

---

## Java-first Principal Hardening v2 (Binding)

This section defines Java-specific, measurable hardening rules for business and test code.

### JPH2-1 Risk tiering by touched surface (binding)

The workflow MUST classify changed scope before implementation and gate reviews
using the canonical tiering contract from `rules.risk-tiering.md` (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`).

`JPH2` adds Java-specific obligations per canonical tier; it does not define a parallel tier system.

### JPH2-2 Mandatory evidence pack per tier (binding)

For `TIER-LOW` (per canonical tiering), evidence requires:
- build
- changed-module tests

For `TIER-MEDIUM`, evidence requires:
- build
- changed-module tests
- at least one negative-path test for changed behavior

For `TIER-HIGH`, evidence requires:
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

## Examples (GOOD/BAD)

GOOD:
- Controller validates input, maps DTO, and delegates to a use-case service with no business branching.

BAD:
- Controller directly writes repository state and branches on domain rules.

GOOD:
- Tests use injected `Clock` with fixed instant and assert behavior-oriented outcomes.

BAD:
- Tests rely on `Instant.now()` and `Thread.sleep(...)` for async synchronization.

---

## Anti-Patterns Catalog (Binding)

Each anti-pattern below includes an explanation of **why** it is harmful. The workflow MUST avoid generating code that matches these anti-patterns and MUST flag them during plan review (Phase 4 step 6) and code review (Phase 5).

### AP-J01: Fat Controller

**Pattern:** Controller contains business logic (if/else branching on domain rules, calculations, multi-step orchestration).

**Why it is harmful:**
- Violates separation of concerns: controllers become untestable without full HTTP context.
- Business rules become duplicated when the same logic is needed from a different trigger (messaging, CLI, scheduled task).
- Makes unit testing expensive: requires MockMvc/WebMvcTest instead of plain JUnit.

**Detection:** `if`/`switch` statements in controller methods that branch on domain state rather than HTTP concerns (content negotiation, auth).

---

### AP-J02: Anemic Domain Model

**Pattern:** Entities are pure data holders with only getters/setters; all business logic lives in services.

**Why it is harmful:**
- Domain invariants are scattered across services and impossible to enforce consistently.
- Every new service that touches the entity risks violating invariants differently.
- Testing requires integration-level setup because logic is coupled to service orchestration.

**Detection:** Entity classes with no methods beyond getters/setters/constructors; services with inline validation/calculation that belongs to one entity.

---

### AP-J03: Nondeterministic Tests

**Pattern:** Tests use `Instant.now()`, `Math.random()`, `UUID.randomUUID()`, or `Thread.sleep()` without deterministic control.

**Why it is harmful:**
- Creates flaky tests that pass locally but fail in CI (or vice versa).
- Impossible to reproduce failures deterministically.
- `Thread.sleep()` wastes CI time and masks real timing bugs.

**Detection:** Direct calls to `Instant.now()`, `System.currentTimeMillis()`, `Thread.sleep()`, or `UUID.randomUUID()` in test code without injectable seams.

---

### AP-J04: Entity Exposure Through API

**Pattern:** JPA entities are returned directly from controllers or used as request/response models.

**Why it is harmful:**
- Exposes internal persistence structure (column names, lazy proxies, version fields) to API consumers.
- Makes it impossible to evolve the database schema without breaking the API contract.
- Lazy-loading exceptions (`LazyInitializationException`) leak to API responses.
- Serialization of bidirectional relationships causes infinite recursion or `StackOverflowError`.

**Detection:** Controller return types or `@RequestBody` types that are `@Entity`-annotated classes.

---

### AP-J05: Swallowed Exceptions

**Pattern:** `catch (Exception e) { log.error(...); }` with no rethrow, wrapping, or meaningful recovery.

**Why it is harmful:**
- Silently converts errors into successful responses, corrupting data or misleading consumers.
- Makes debugging production issues extremely difficult: errors are logged but not propagated.
- Violates fail-fast principle: the system continues in an undefined state.

**Detection:** `catch` blocks that only log without rethrowing, wrapping, or returning an error response.

---

### AP-J06: God Service

**Pattern:** A single service class with 10+ methods spanning multiple unrelated use cases.

**Why it is harmful:**
- Violates Single Responsibility Principle: changes to one use case risk breaking others.
- Impossible to test in isolation: setup requires mocking many unrelated dependencies.
- Leads to circular dependencies as the god service grows to depend on everything.

**Detection:** Service classes with more than 5-7 public methods or more than 4-5 injected dependencies.

---

### AP-J07: Field Injection

**Pattern:** Using `@Autowired` on fields instead of constructor injection.

**Why it is harmful:**
- Makes dependencies invisible: you cannot see what a class depends on without reading every field.
- Makes unit testing harder: you need reflection or Spring context to inject dependencies.
- Hides excessive coupling: constructor injection naturally reveals when a class has too many dependencies.

**Detection:** `@Autowired` annotations on fields (not constructors).

---

### AP-J08: Test Overspecification

**Pattern:** Tests verify internal method calls (`verify(mock, times(1))`) instead of behavioral outcomes.

**Why it is harmful:**
- Tests break on every refactoring even when behavior is unchanged.
- Tests become a mirror of the implementation, providing no safety net for change.
- False sense of coverage: tests "pass" but verify nothing meaningful.

**Detection:** Heavy use of Mockito `verify(...)` with exact call counts and argument matchers, without corresponding behavioral assertions.

---

### AP-J09: Transaction Boundary Leak

**Pattern:** Making external HTTP/messaging calls inside a database transaction.

**Why it is harmful:**
- Holds database connections open during network I/O, risking connection pool exhaustion.
- If the external call fails after the DB commit, data is inconsistent; if before, the transaction is unnecessarily long.
- Creates tight coupling between database state and external system availability.

**Detection:** `@Transactional` methods that call `RestTemplate`, `WebClient`, `KafkaTemplate`, or similar external clients.

---

### AP-J10: Mutable DTO / Setter-Based Domain Mutation

**Pattern:** Domain objects or DTOs with public setters used for ad-hoc field assignment throughout the codebase.

**Why it is harmful:**
- Impossible to enforce invariants: any code can set any field to any value at any time.
- Domain objects can exist in invalid states between setter calls.
- Makes it impossible to reason about object state at any given point in the code.

**Detection:** `@Data` on entities/domain objects; public setters on business-critical fields; scattered `entity.setField(...)` calls outside domain methods.

---

## Troubleshooting

1) Symptom: Contract gate fails after endpoint change
- Cause: implementation changed without matching contract or regeneration
- Fix: align contract first, regenerate boundary artifacts, and rerun repo-native contract checks.

2) Symptom: Async tests are flaky in CI
- Cause: timing-based synchronization (`sleep`) or uncontrolled clock/randomness
- Fix: replace sleeps with Awaitility/retryable assertions and use deterministic seams (`Clock`, fixed IDs/order).

3) Symptom: Architecture gate reports boundary violations
- Cause: business logic leaked into controllers/adapters or cross-module import drift
- Fix: move branching into use-case/service layer and restore module/layer boundaries.

---

See shared governance rulebooks for canonical RTN/CAL contracts:
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
