# Backend Java Profile Rulebook (v2.1)
Backend Java Profile Rulebook (v2.1)

This document defines **backend Java (Spring Boot)** profile rules.
It is applied **in addition** to the Core Rulebook (`rules.md`) and the Master Prompt (`master.md`).

**Intent:** enforce *provable* best-practice engineering defaults so the system reliably produces  
**top-tier business code and tests** — not by intention, but by **verified evidence**.

Priority order on conflict:
`master.md` > `rules.md` (Core) > this profile.

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
