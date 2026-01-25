# profiles/rules.backend-java.md
Backend Java Profile Rulebook

This document defines **backend Java** (Spring Boot) specific rules.
It is applied **in addition** to the Core Rulebook (`rules.md`) and the Master Prompt (`master.md`).

If this profile conflicts with the Core Rulebook or Master Prompt, the priority order applies:
`master.md` > `rules.md` (Core) > this profile.

---

## 1. Technology Stack (Backend Java)

Unless the repository provides a different stack explicitly (and it is allowed by priority rules), assume:

- Java 21
- Spring Boot
- Maven (or Gradle if repo evidence shows it)
- OpenAPI Generator (if OpenAPI contract-first is used)
- Flyway or Liquibase for DB migrations (repo-driven)

---

## 2. Code Style (Backend Java)

- Google Java Style
- 4-space indentation
- no wildcard imports
- alphabetical imports
- no `TODO` / `FIXME` in production code
- prefer explicitness over cleverness (review robustness)

---

## 3. Architecture Guidelines (Backend Java)

### 3.1 Layering (Default)

- strict separation of **Domain / Application / Infrastructure**
- no business logic in controllers
- services must be domain-cohesive
- repositories are persistence-only (no domain logic)
- mappers are explicit (MapStruct or manual, repo-driven)
- central exception handling via `@ControllerAdvice`
- avoid “god objects” (single class owning many unrelated responsibilities)

### 3.2 Architecture Pattern Catalog (Detectable)

A) **Layered architecture (default)**
- Controller → Service → Repository
- DTOs in controller layer, entities in persistence layer
- mapping between layers is mandatory

B) **Hexagonal architecture (ports & adapters)**
- isolated domain core
- ports (interfaces) define dependencies
- adapters implement ports

C) **CQRS**
- commands mutate state (void or event)
- queries return data (read models)
- no mixed methods

**Gate check expectations (when architecture is evaluated):**
- which pattern is present (detect via package/module structure)?
- is it applied consistently?
- are there layer violations (e.g., Controller → Repository directly)?

**Typical blockers:**
- controller contains business logic (>10 meaningful lines in a method, excluding mapping)
- repository contains business/business-domain queries that belong to the service layer
- service contains DB-specific code that belongs in persistence/infrastructure

---

## 4. API Contracts (Backend Java)

- If OpenAPI exists in scope, it is authoritative over code (contract-first).
- Generated code must never be edited manually.
- Breaking changes only via versioning or spec changes.

If the repository is code-first (no authoritative OpenAPI present), document the mode explicitly and treat code as authoritative, but do not fabricate missing contracts.

---

## 5. Business Rules Discovery (Backend Java)

Purpose:
Business rules are often undocumented and exist only in code/DB/tests.
When the workflow requires it (or when risk is high), extract business rules **before** implementation planning.

### 5.1 Detection Patterns (Examples)

Pattern 1: Guard clauses in services

```java
public void deletePerson(Long id) {
    Person person = findById(id);
    if (!person.getContracts().isEmpty()) {
        throw new BusinessException("CONTRACTS_ACTIVE", "Person has active contracts");
    }
    repository.delete(person);
}
```

Pattern 2: Bean Validation

```java
@Entity
public class Person {
    @AssertTrue(message = "Person must be adult")
    public boolean isAdult() {
        return age >= 18;
    }
}
```

Pattern 3: DB constraints

```sql
ALTER TABLE person ADD CONSTRAINT email_unique UNIQUE (email);
ALTER TABLE contract ADD CONSTRAINT valid_status
  CHECK (status IN ('DRAFT', 'ACTIVE', 'CANCELLED'));
ALTER TABLE contract ADD CONSTRAINT fk_person_contract
  FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE RESTRICT;
```

Pattern 4: Test names (implicit rules)

```java
@Test
void deletePerson_shouldThrowException_whenContractsActive() { ... }
```

Pattern 5: Exception messages / error codes

```java
throw new BusinessException("PERSON_UNDERAGE", "Person must be at least 18 years old");
```

Pattern 6: State transition guards (state machine)

```java
if (this.status == ContractStatus.CANCELLED) { ... }
```

Pattern 7: Query filters (soft delete)

```java
@Query("SELECT p FROM Person p WHERE p.deleted = false")
List<Person> findAllActive();
```

### 5.2 Output Format (Binding When Executed)

If business rules extraction is executed, produce a structured inventory:

- stable IDs (e.g., `BR-001`)
- rule statement
- source(s) as `path:line` or excerpt references
- enforcement classification: Code | DB Constraint | Test | Validation
- critical gaps analysis (tested-but-not-enforced, DB-only, etc.)

---

## 6. Test Rules (Backend Java)

### 6.1 Frameworks (Repo-First Defaults)

- JUnit 5
- Mockito
- slice tests: `@DataJpaTest`, `@WebMvcTest` (as applicable)
- integration tests: Testcontainers (only when justified by scope/risk/ticket)
- architecture/contract tests: ArchUnit (repo-driven)

### 6.2 Test Structure & Obligations

- Given / When / Then structure is mandatory
- expressive names: `methodName_shouldBehavior_whenCondition`
- one test = one assertion focus (avoid unrelated multi-asserts)
- add tests for changed/new behavior; no cosmetic-only tests

### 6.3 Coverage (Repo-First; Default Target)

Unless repo defines stricter standards:
- ≥ 80% line coverage for changed/new logic
- ≥ 75% branch coverage for changed/new logic

If mutation testing (e.g., PIT) is established in the repo, follow repo standards.

### 6.4 Mandatory Coverage Matrix (For Public Methods)

For every public method in Service/Repository/Controller, the following categories must be considered and implemented as applicable:

- HAPPY_PATH
- NULL_INPUT (each parameter)
- EMPTY_INPUT (collections where applicable)
- NOT_FOUND (query endpoints/services)
- BOUNDARY (0, -1, MAX, min/max lengths as applicable)
- CONSTRAINT_VIOLATION (DB constraints, Bean Validation)
- STATE_INVALID (business rule violation)
- AUTHORIZATION (if security annotations/guards exist)

### 6.5 Heavy Integration Tests (Conditional)

“Heavy integration tests” include high-overhead setups like:
- Testcontainers with multiple dependencies
- embedded brokers (e.g., Kafka) if established in the repo
- BDD frameworks (e.g., Cucumber) if established in the repo

Rules:
- prefer unit/slice tests for internal business logic changes
- add/expand heavy tests only if:
  - external integration surfaces change (REST contract/events/adapters), or
  - risk cannot be covered via unit/slice, or
  - the ticket explicitly requests integration/E2E evidence

If heavy tests are not used, document the justification and how risks are covered.


### 6.6 Concrete Test Patterns (Mandatory)

**Pattern 1: Exception testing**

Avoid overly generic assertions:

```java
@Test
void shouldThrowException() {
    assertThrows(Exception.class, () -> service.delete(1L));
}
```

Prefer specific exceptions and verifiable attributes (code/message):

```java
@Test
void deleteEntity_shouldThrowBusinessException_whenPreconditionsNotMet() {
    // Given
    var entity = aDomainEntityWithViolatingState();
    when(repository.findById(entity.getId())).thenReturn(Optional.of(entity));

    // When/Then
    BusinessException ex = assertThrows(
        BusinessException.class,
        () -> service.delete(entity.getId())
    );
    assertThat(ex.getCode()).isEqualTo("PRECONDITION_FAILED");
    assertThat(ex.getMessage()).contains("cannot be deleted");

    verify(repository, never()).save(any());
    verifyNoMoreInteractions(repository);
}
```

**Pattern 2: State verification (persistence + side effects)**

```java
@Test
void updateEntity_shouldPersistChanges_andPublishEvent() {
    // Given
    var existing = repository.save(aDomainEntity().build());
    var request = validUpdateRequest();

    // When
    var result = service.update(existing.getId(), request);

    // Then
    assertThat(result.getName()).isEqualTo(request.name());

    var persisted = repository.findById(existing.getId()).orElseThrow();
    assertThat(persisted.getName()).isEqualTo(request.name());

    verify(eventPublisher).publish(any(DomainEvent.class));
    verifyNoMoreInteractions(eventPublisher);
}
```

**Pattern 3: Isolation testing (transactions)**

If a method is transactional and performs multiple steps, verify rollback behavior when a later step fails:

```java
@Test
void createEntity_shouldRollback_whenSubsequentOperationFails() {
    // Given
    var request = validCreateRequest();
    doThrow(new RuntimeException("Simulated failure"))
        .when(auditService).logCreation(any());

    // When
    assertThrows(RuntimeException.class, () -> service.create(request));

    // Then
    assertThat(repository.findAll()).isEmpty();
}
```

### 6.7 Test Data Management (Mandatory)

Forbidden:
- hard-coded IDs
- hard-coded globally reused unique fields (e.g., email)
- shared mutable fixtures across tests

Mandatory: builder/factory helpers for deterministic and low-friction setup:

```java
public final class TestData {
    private TestData() {}

    public static DomainEntityBuilder aDomainEntity() {
        return DomainEntity.builder()
            .name("Test")
            .externalId(UUID.randomUUID().toString());
    }

    public static DomainEntity aDomainEntityWithViolatingState() {
        return aDomainEntity()
            .status(Status.LOCKED)
            .build();
    }
}
```

### 6.8 Mock Verification (Mandatory When Mocks Are Used)

- Every mock interaction must be verified.
- Ensure no unexpected interactions occur.

```java
@Test
void createEntity_shouldCallDependencies_inOrder() {
    // Given
    var request = validCreateRequest();

    // When
    service.create(request);

    // Then
    InOrder inOrder = inOrder(validator, repository, eventPublisher);
    inOrder.verify(validator).validate(request);
    inOrder.verify(repository).save(any());
    inOrder.verify(eventPublisher).publish(any());

    verifyNoMoreInteractions(validator, repository, eventPublisher);
}
```

### 6.9 JUnit Tagging (Conditional, Repo-First)

Tagging is **required** if any of the following is true:
- the repository already uses `@Tag(...)` in a non-trivial way, or
- CI/build config (Surefire/Failsafe) selects tests via tags, or
- repository documentation defines tagging as standard

Recommended tags:
`@Tag("unit")` | `@Tag("slice")` | `@Tag("integration")` | `@Tag("contract")`

If tagging is established:
- all new and modified tests must be tagged
- when editing an existing untagged test, add an appropriate tag

If tagging is not established:
- tag newly created tests
- do not refactor untouched tests solely to add tags

### 6.10 Coverage Evidence (BuildEvidence Coupling)

- Coverage targets apply to **changed/new logic**.
- Claims like “coverage is met” are only allowed if BuildEvidence is provided (command + output snippet).
- Otherwise label as “theoretical / not verified”.

---

## 7. Database / Migrations (Backend Java)

- prefer migrations (Flyway/Liquibase) over manual SQL changes
- scripts must be traceable and reviewable
- if repo uses Flyway, follow naming/version conventions and idempotency rules established in the repository

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
