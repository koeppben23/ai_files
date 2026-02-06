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
- When loaded, templates MUST be followed **verbatim** (placeholders-only substitution).

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
