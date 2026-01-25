# rules.md

Technical Rulebook for AI-Assisted Development

This document contains all technical, architectural, testing, and formatting rules.
Operational behavior (phases, session state, hybrid mode, priorities) is defined in the Master Prompt.
This document is secondary to the Master Prompt, but takes precedence over ticket text.

---

# 1. Role & Responsibilities

The AI acts as:

* Senior Expert Java Engineer (20+ years of experience)
* Lead backend engineer responsible for production-grade enterprise systems
* Expert in Spring Boot, architecture, and clean code
* Focused on deterministic implementations, reproducibility, and review robustness
* Zero tolerance for assumptions without evidence

Responsible for:

* correct technical planning
* implementable, consistent solutions
* complete tests
* stable, deterministic outcomes
* strict adherence to scope lock and no fabrication

---

# 2. Input Artifacts (Inputs)

Required:
- A repository as an archive artifact (e.g., ZIP/TAR/working copy) OR a repository indexed by OpenCode
- Optional: additional artifacts (e.g., OpenAPI specs, DB dumps, CSV/Excel) if provided in the ticket/session

Optional:
- API specifications (OpenAPI)
- additional project artifacts (e.g., documentation, diagrams, sample payloads)

The AI may only access artifacts that were actually provided (scope lock).

Examples (non-normative):
- backend-service repository
- integration/adapter repository
- frontend repository (if explicitly in scope)

---

# 3. Archive Artifacts & Technical Access

## 3.1 Definition: Archive Artifacts

A locally available repository (working copy) is treated as an extracted archive artifact.
Archive artifacts contain multiple files/directories and must be extracted for real.

## 3.2 Binding technical access

All provided archive artifacts must be fully and actually extracted before any analysis.

Binding rules:

* no heuristic assumptions
* no simulated content
* no reconstruction from experience

Failure case (artifacts not extractable/missing):

* abort analysis in NORMAL mode
* immediately switch to the mode defined in Chapter 10 (DEGRADED/BLOCKED)
* explicitly report the error and do not mark any content statements as confirmed

---

# 4. Architecture & Coding Guidelines

## 4.1 Technology Stack

* Java 21
* Spring Boot
* Maven
* OpenAPI Generator

## 4.2 Code Style

* Google Java Style
* 4-space indentation
* no wildcard imports
* alphabetical imports
* no TODO/FIXME in production code

## 4.3 Architecture

* strict separation of Domain / Application / Infrastructure
* no business logic in controllers
* services must be domain-cohesive
* repositories are persistence-only
* mappers explicit (MapStruct or manual)
* central exception handling (`@ControllerAdvice`)
* no god objects

## Architecture Patterns (Phase 5 supplement)

### Pattern catalog (detectable in the repository)

A) Layered architecture (default)

* Controller → Service → Repository
* DTOs in controller layer, entities in repository layer
* mapper between layers is mandatory

B) Hexagonal architecture (ports & adapters)

* isolated domain core
* ports (interfaces) define dependencies
* adapters implement ports

C) CQRS (Command Query Responsibility Segregation)

* commands mutate state (void or event)
* queries return data (read models)
* no mixed methods

**Gate check in Phase 5:**

* Which pattern is present? (auto-detect via package structure)
* Is the pattern applied consistently?
* Are there layer violations? (e.g., Controller → Repository directly)

**Blockers:**

* controller contains business logic (>10 lines in a method)
* repository contains domain/business queries (should live in service layer)
* service contains DB-specific code (should live in repository layer)

## 4.4 API Contracts

* OpenAPI is authoritative over code (contract-first)
* generated code must never be edited manually
* breaking changes only via versioning or spec changes

---

# 5. Discovery Rules (Phase 2 & 3)

## 5.1 Repository analysis

* analyze module tree, class inventory, tests, configuration, and Flyway scripts
* no interpretation without source evidence

## 5.2 API analysis

* capture endpoints, methods, paths, schemas, and versions
* no validation or mapping logic in this phase

# 5.3 Business Rules Discovery (Phase 1.5)

## 5.3.1 Purpose

Business rules are often undocumented and exist only in code/DB/tests.
Phase 1.5 extracts these rules BEFORE implementation planning.

This reduces business-logic gaps from ~50% to <15%.

## 5.3.2 Detection patterns

### Pattern 1: Guard clauses in services

**Detected as a business rule:**

```java
public void deletePerson(Long id) {
    Person person = findById(id);
    if (!person.getContracts().isEmpty()) {  // ← BR: person with contracts cannot be deleted
        throw new BusinessException("CONTRACTS_ACTIVE", "Person has active contracts");
    }
    repository.delete(person);
}
```

**Extracted rule:**

```text
BR-001: Person
Rule: A person may be deleted only if contracts.isEmpty()
Source: PersonService.java:42 (if-guard)
Enforcement: Code (Guard Clause)
```

### Pattern 2: Bean Validation

**Detected as a business rule:**

```java
@Entity
public class Person {
    @AssertTrue(message = "Person must be adult")
    public boolean isAdult() {  // ← BR: only adults allowed
        return age >= 18;
    }
}
```

**Extracted rule:**

```text
BR-002: Person
Rule: Person.age must be >= 18
Source: Person.java:@AssertTrue (isAdult)
Enforcement: Bean Validation
```

### Pattern 3: DB constraints

**Detected as a business rule:**

```sql
-- V001__schema.sql
ALTER TABLE person ADD CONSTRAINT email_unique UNIQUE (email);  -- ← BR: email must be unique

ALTER TABLE contract ADD CONSTRAINT valid_status
  CHECK (status IN ('DRAFT', 'ACTIVE', 'CANCELLED'));  -- ← BR: only defined statuses

ALTER TABLE contract ADD CONSTRAINT fk_person_contract
  FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE RESTRICT;  -- ← BR: delete restriction
```

**Extracted rules:**

```text
BR-003: Person
Rule: Person.email must be unique
Source: V001__schema.sql:UNIQUE (email_unique)
Enforcement: DB Constraint

BR-004: Contract
Rule: Contract.status only DRAFT|ACTIVE|CANCELLED
Source: V001__schema.sql:CHECK (valid_status)
Enforcement: DB Constraint

BR-005: Contract
Rule: A person with contracts cannot be deleted
Source: V001__schema.sql:FK ON DELETE RESTRICT
Enforcement: DB Constraint
```

### Pattern 4: Test names (implicit rules)

**Detected as a business rule:**

```java
@Test
void deletePerson_shouldThrowException_whenContractsActive() {  // ← BR documented in test
    // Given
    Person person = aPersonWithActiveContracts();

    // When/Then
    assertThrows(BusinessException.class, () -> service.deletePerson(person.getId()));
}

@Test
void approvePerson_shouldThrowException_whenUnder18() {  // ← BR: minimum age
    // ...
}
```

**Extracted rules:**

```text
BR-006: Person
Rule: person with active contracts cannot be deleted (implied from test)
Source: PersonServiceTest.java:deletePerson_shouldThrowException_whenContractsActive
Enforcement: Tested (must verify code enforcement!)

BR-007: Person
Rule: person must be >= 18 years old for approval
Source: PersonServiceTest.java:approvePerson_shouldThrowException_whenUnder18
Enforcement: Tested (must verify code enforcement!)
```

### Pattern 5: Exception messages

**Detected as a business rule:**

```java
if (person.getAge() < 18) {
    throw new BusinessException(
        "PERSON_UNDERAGE",  // ← error code
        "Person must be at least 18 years old"  // ← BR description
    );
}

if (!contract.canBeApproved()) {
    throw new BusinessException(
        "APPROVAL_PRECONDITIONS_NOT_MET",
        String.format("Contract %s cannot be approved: missing signatures", contract.getId())
    );
}
```

**Extracted rules:**

```text
BR-008: Person
Rule: person must be at least 18 years old
Source: PersonService.java:exception-message (PERSON_UNDERAGE)
Enforcement: Code (Exception)

BR-009: Contract
Rule: contract requires all signatures for approval
Source: ContractService.java:exception-message (APPROVAL_PRECONDITIONS_NOT_MET)
Enforcement: Code (Exception)
```

### Pattern 6: State transition logic

**Detected as a business rule:**

```java
public void transitionStatus(ContractStatus newStatus) {
    if (this.status == ContractStatus.CANCELLED) {
        throw new BusinessException("INVALID_STATE_TRANSITION",
            "Cannot transition from CANCELLED state");
    }

    if (this.status == ContractStatus.ACTIVE && newStatus == ContractStatus.DRAFT) {
        throw new BusinessException("INVALID_STATE_TRANSITION",
            "Cannot revert from ACTIVE to DRAFT");
    }

    this.status = newStatus;
}
```

**Extracted rule:**

```text
BR-010: Contract
Rule: transition CANCELLED → * is not allowed
Source: Contract.java:transitionStatus (state guard)
Enforcement: Code (State Machine)

BR-011: Contract
Rule: transition ACTIVE → DRAFT is not allowed
Source: Contract.java:transitionStatus (state guard)
Enforcement: Code (State Machine)
```

### Pattern 7: Query filter (soft delete)

**Detected as a business rule:**

```java
@Repository
public interface PersonRepository extends JpaRepository {

    @Query("SELECT p FROM Person p WHERE p.deleted = false")
    List findAllActive();  // ← BR: deleted persons are invisible

    @Query("SELECT p FROM Person p WHERE p.id = :id AND p.deleted = false")
    Optional findByIdActive(@Param("id") Long id);
}
```

**Extracted rule:**

```text
BR-012: Person
Rule: deleted=true persons are invisible in default queries
Source: PersonRepository.java:findAllActive (query filter)
Enforcement: Query Filter (manual)
```

## 5.3.3 Anti-patterns (NOT a business rule)

### ❌ Technical validation (not a BR)

```java
// NOT a business rule:
if (id == null) throw new IllegalArgumentException("ID required");  // technical
Objects.requireNonNull(person, "Person must not be null");           // technical
```

### ❌ Framework constraints (not a BR)

```java
// NOT a business rule:
@NotNull        // technical (non-null)
@Size(max=255)  // technical (DB length)
@Email          // technical (format validation)
private String email;
```

### ❌ Logging/debugging (not a BR)

```java
// NOT a business rule:
log.info("Deleting person {}", id);
log.debug("Contract status changed from {} to {}", oldStatus, newStatus);
```

### ❌ Performance optimizations (not a BR)

```java
// NOT a business rule:
@Cacheable("persons")
@Transactional(readOnly = true)
```

## 5.3.4 Confidence rules

The number of business rules found affects the confidence level:

| Business rules found | Repository size | Confidence adjustment | Interpretation                           |
| -------------------- | --------------- | --------------------- | ---------------------------------------- |
| 0–2                  | >50 classes     | -20%                  | Critical gap: almost no BRs documented   |
| 3–5                  | >50 classes     | -10%                  | Gap likely: few BRs for a large codebase |
| 6–10                 | >50 classes     | +0%                   | Acceptable: baseline BRs exist           |
| 10+                  | >50 classes     | +10%                  | Well documented: extensive BR coverage   |
| any                  | <30 classes     | +0%                   | CRUD project: BRs optional               |

**Example:**

```text
Repository: 67 classes
Business rules found: 3 (Code:1, DB:1, Tests:1)

Confidence adjustment: -10%
Reasoning: A large codebase with only 3 documented rules suggests missing BR documentation.
```

## 5.3.5 Critical gaps

A critical gap exists if:

1. **Test without code enforcement:**

   * a test documents a BR (e.g., `shouldThrowException_whenContractsActive`)
   * but there is no corresponding guard clause in service code

2. **Code without test:**

   * service contains a BR guard clause
   * but there is no corresponding exception test

3. **DB constraint without code check:**

   * DB has `ON DELETE RESTRICT`
   * but service does not prevent deletion (race condition / poor UX)

**Output format for critical gaps:**

```text
Critical-Gaps: [
  "Contract.approve() has explicit test (approvePerson_shouldThrowException_whenPreconditionsFail)
   but no precondition checks in code → Test will ALWAYS fail",

  "Person.delete() has DB constraint ON DELETE RESTRICT
   but no code-level check → user receives DB error instead of BusinessException"
]
```

## 5.3.6 Output format

**Full example:**

```text
[BUSINESS_RULES_INVENTORY]
Total-Rules: 15
By-Source: [Code:6, DB:4, Tests:5, Validation:3]
By-Entity: [Person:8, Contract:5, Address:2]

Rules:
| Rule-ID | Entity   | Rule                                     | Source                    | Enforcement           |
|---------|----------|-------------------------------------------|---------------------------|-----------------------|
| BR-001  | Person   | contracts.isEmpty() required for delete   | PersonService.java:42     | Code (Guard)          |
| BR-002  | Person   | age >= 18                                 | Person.java:@AssertTrue   | Bean Validation       |
| BR-003  | Person   | email unique                              | V001__schema.sql:UNIQUE   | DB Constraint         |
| BR-004  | Person   | deleted=true persons invisible in queries | PersonRepository.java:15  | Query Filter          |
| BR-005  | Contract | status only DRAFT→ACTIVE→CANCELLED        | ContractService.java:67   | Code (State Machine)  |
| BR-006  | Contract | no transition from CANCELLED              | Contract.java:transitionStatus | Code (State Guard) |
| BR-007  | Contract | person_id FK ON DELETE RESTRICT           | V002__contracts.sql:FK    | DB Constraint         |
| BR-008  | Contract | all signatures required for approval      | ContractService.java:approve | Code (Precondition) |
| BR-009  | Contract | approve() preconditions tested            | ContractServiceTest.java:L87 | Test ONLY           |
| ...     | ...      | ...                                       | ...                       | ...                   |

Critical-Gaps: [
  "BR-009 (Contract.approve preconditions): Tested but NOT implemented in code",
  "BR-007 (FK ON DELETE RESTRICT): DB constraint exists but no code-level check → poor UX"
]

Confidence-Impact: -10% (15 rules for 67 classes is below expected threshold)
[/BUSINESS_RULES_INVENTORY]
```

## 5.3.7 Integration into subsequent phases

### Phase 4 (planning)

* the plan MUST reference all relevant BRs from the inventory
* missing BR checks must be marked as `[INFERENCE-ZONE: Missing BR-Check]`
* new BRs (not in inventory) must be labeled as `[NEW-RULE]`

### Phase 5.4 (business rules compliance)

* verify: are all inventory BRs traceable in plan/code/tests?

#### Definition of Done — Business Rules (binding)

* ≥ 80% of identified BRs are referenced in at least plan OR code OR tests
* 0 critical BRs with zero coverage (plan/code/tests)

#### Hard gate rules (binding)

The following situations automatically enforce a gate status:

1. `business-rules-gap-detected`

   * > 20% of BRs are referenced in neither plan nor code nor tests

2. `enforcement-missing`

   * BR exists ONLY in tests, but cannot be found in implementation (code/DB constraint)

3. `implicit-business-logic`

   * business behavior exists but cannot be mapped to an explicit BR-ID in the inventory

In these cases:

* Phase 5.4 MUST be executed
* the assistant may NOT advance to the next phase

### Phase 6 (implementation QA)

* every BR MUST be traceable in at least code OR DB constraint OR tests
* `enforcement-missing` is a blocker if the BR is classified as critical

## 5.3.8 Example: full detection workflow

**Given: `PersonService.deletePerson()`**

**Step 1: scan code**

```java
public void deletePerson(Long id) {
    Person person = repository.findById(id).orElseThrow();
    if (!person.getContracts().isEmpty()) {  // ← found: BR-001
        throw new BusinessException("CONTRACTS_ACTIVE");
    }
    repository.delete(person);
}
```

→ extracted: BR-001 (code guard)

**Step 2: scan tests**

```java
@Test
void deletePerson_shouldThrowException_whenContractsActive() {  // ← confirms: BR-001
    // ...
}
```

→ confirms: BR-001 (test exists)

**Step 3: scan DB**

```sql
ALTER TABLE contract ADD CONSTRAINT fk_person_contract
  FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE RESTRICT;  -- ← found: BR-001
```

→ confirms: BR-001 (DB constraint exists)

**Result:**

```text
BR-001: Person
Rule: A person with contracts cannot be deleted
Sources: [PersonService.java:42, PersonServiceTest.java:L87, V002__contracts.sql:FK]
Enforcement: Code ✓ | Test ✓ | DB ✓
Consistency: CONSISTENT (all 3 layers enforce the rule)
```

---

# 6. Implementation Rules (Phase 4)

## 6.1 Plan

* numbered, complete, and technically executable.

## 6.2 Code changes

* output as unified diffs
* max 300 lines per block
* max 5 files per response

## 6.3 Quality

* no duplicate code paths
* no silent refactorings (only scope-relevant changes)
* validate all inputs (Bean Validation / domain)
* clean logging (SLF4J)
* transactions (`@Transactional`) only where domain-relevant

## 6.4 DB / Flyway

* scripts must be idempotent, traceable, and tested

---

# 7. Test Rules

## 7.1 Coverage

* ≥80% coverage for changed or new logic

## 7.2 Test types

* unit tests (JUnit 5, Mockito)
* slice tests (`@DataJpaTest`, `@WebMvcTest`)
* integration tests (Testcontainers)
* contract tests (ArchUnit)

## 7.2.1 Heavy integration tests (conditional)

Definition:
“Heavy integration tests” are tests with typically high runtime/setup overhead,
e.g., Cucumber, Testcontainers, Embedded Kafka, external system adapters.

Rule (repo-first):

1. Default strategy:

   * prefer unit/slice tests for the majority of tickets
   * heavy integration tests are NOT added/expanded automatically
     when the change only affects internal business logic

2. Mandatory trigger:
   Heavy integration tests MUST be added/expanded if at least one applies:
   A) change affects external integration surfaces (REST contract, events, Kafka, external adapters), OR
   B) change affects configuration/mapping that can only be validated integratively, OR
   C) the ticket explicitly requests integration/E2E evidence

3. Evidence:

   * if heavy integration tests are not executed/expanded, the plan (Phase 4)
     must include a brief justification (“Not needed because ...”) and which unit/slice tests
     cover the risk instead

## 7.3 Structure & obligations

### 7.3.1 Test architecture

* Given / When / Then structure (mandatory)
* expressive test names following: `methodName_shouldBehavior_whenCondition`
* one test = one assertion focus (no multi-assertions for unrelated aspects)
* at least one new test class per new production class

### 7.3.2 Mandatory test coverage matrix

For EVERY public method in Service/Repository/Controller, the following test cases MUST exist:

| Test category        | Description                              | Example                                                  |
| -------------------- | ---------------------------------------- | -------------------------------------------------------- |
| HAPPY_PATH           | standard case, all inputs valid          | findById_shouldReturnPerson_whenIdExists                 |
| NULL_INPUT           | test each parameter individually as null | findById_shouldThrowException_whenIdIsNull               |
| EMPTY_INPUT          | empty lists/collections                  | findAll_shouldReturnEmptyList_whenNoDataExists           |
| NOT_FOUND            | resource does not exist                  | findById_shouldThrowNotFoundException_whenIdDoesNotExist |
| BOUNDARY             | boundary values (0, -1, MAX_VALUE)       | createPerson_shouldReject_whenAgeIsNegative              |
| CONSTRAINT_VIOLATION | DB constraints, Bean Validation          | createPerson_shouldThrowException_whenEmailDuplicate     |
| STATE_INVALID        | business rule violated                   | deletePerson_shouldThrowException_whenContractsActive    |
| AUTHORIZATION        | access without permission                | findById_shouldThrowAccessDenied_whenUserNotOwner        |

### 7.3.3 Special test requirements by method type

A) Query methods (SELECT)

Mandatory:

* findById_shouldReturnPerson_whenExists
* findById_shouldThrowNotFoundException_whenNotExists
* findById_shouldNotReturnDeletedEntities (CRITICAL)
* findById_shouldNotLeakSensitiveData_whenUnauthorized (CRITICAL)

B) Command methods (INSERT/UPDATE/DELETE)

Mandatory:

* createPerson_shouldSaveAndReturnEntity_whenValid
* createPerson_shouldThrowValidationException_whenEmailInvalid
* createPerson_shouldThrowException_whenEmailDuplicate (CRITICAL)
* createPerson_shouldRollbackTransaction_whenSaveFails (CRITICAL)

C) State transition methods (status changes)

Mandatory:

* approve_shouldChangeStatus_whenAllConditionsMet
* approve_shouldThrowException_whenAlreadyApproved (CRITICAL)
* approve_shouldThrowException_whenPreconditionsFail (CRITICAL)
* approve_shouldNotAffectOtherEntities (CRITICAL — isolation)

D) Methods with external calls (APIs, events)

Mandatory:

* syncPerson_shouldCallExternalApi_whenValid
* syncPerson_shouldRetry_whenApiTemporarilyDown (CRITICAL)
* syncPerson_shouldNotCorruptData_whenApiReturnsError (CRITICAL)
* syncPerson_shouldLogError_whenMaxRetriesExceeded (CRITICAL)

### 7.3.4 Concrete test patterns (mandatory)

Pattern 1: Exception testing

WRONG (too generic):

```java
@Test void shouldThrowException() {
    assertThrows(Exception.class, () -> service.delete(1L));
}
```

RIGHT (specific + message/code checks):

```java
@Test void deletePerson_shouldThrowBusinessException_whenContractsActive() {
    // Given
    Person person = createPersonWithActiveContracts();

    // When/Then
    BusinessException ex = assertThrows(
        BusinessException.class,
        () -> service.deletePerson(person.getId())
    );
    assertThat(ex.getCode()).isEqualTo("ACTIVE_CONTRACTS_EXIST");
    assertThat(ex.getMessage()).contains("Person has 3 active contracts");
}
```

Pattern 2: State verification

WRONG (only return value tested):

```java
@Test void shouldUpdatePerson() {
    Person result = service.update(person);
    assertNotNull(result);
}
```

RIGHT (state + side effects):

```java
@Test void updatePerson_shouldPersistChanges_andSendEvent() {
    // Given
    Person existing = repository.save(createPerson("John", "Doe"));
    PersonUpdateRequest request = new PersonUpdateRequest("Jane", "Doe");

    // When
    Person result = service.update(existing.getId(), request);

    // Then
    assertThat(result.getFirstName()).isEqualTo("Jane");

    // Verify persistence
    Person persisted = repository.findById(existing.getId()).orElseThrow();
    assertThat(persisted.getFirstName()).isEqualTo("Jane");

    // Verify side effects
    verify(eventPublisher).publish(argThat(event ->
        event.getType().equals("PERSON_UPDATED") &&
        event.getPersonId().equals(existing.getId())
    ));
}
```

Pattern 3: Isolation testing (transactions)

```java
@Test void createPerson_shouldRollbackTransaction_whenSubsequentOperationFails() {
    // Given
    PersonCreateRequest request = validRequest();
    doThrow(new RuntimeException("Simulated failure"))
        .when(auditService).logCreation(any());

    // When
    assertThrows(RuntimeException.class, () -> service.createPerson(request));

    // Then - verify nothing was persisted
    assertThat(repository.findAll()).isEmpty();
}
```

### 7.3.5 Test data management

FORBIDDEN:

```java
// Hardcoded magic values:
Person person = new Person();
person.setId(1L);               // What if tests run in parallel?
person.setEmail("test@test.com"); // What about a second run?
```

MANDATORY:

```java
// Test data builder pattern:
public class PersonTestDataBuilder {
    private static final AtomicLong ID_GENERATOR = new AtomicLong(1);

    public static Person.PersonBuilder aPerson() {
        return Person.builder()
            .id(ID_GENERATOR.getAndIncrement())
            .email("person-" + UUID.randomUUID() + "@test.com")
            .firstName("Test")
            .lastName("Person")
            .createdAt(Instant.now());
    }

    public static Person aPersonWithActiveContracts() {
        return aPerson()
            .contracts(List.of(
                aContract().status(ContractStatus.ACTIVE).build()
            ))
            .build();
    }
}

// Usage in tests:
@Test void test() {
    Person person = aPerson().firstName("John").build();
    // ...
}
```

### 7.3.6 Mock verification (mandatory)

For EVERY mock, verification is mandatory:

```java
@Test void createPerson_shouldCallDependencies_inCorrectOrder() {
    // Given
    PersonCreateRequest request = validRequest();

    // When
    service.createPerson(request);

    // Then - verify call order
    InOrder inOrder = inOrder(validator, repository, eventPublisher);
    inOrder.verify(validator).validate(request);
    inOrder.verify(repository).save(any(Person.class));
    inOrder.verify(eventPublisher).publish(any(PersonCreatedEvent.class));

    // Then - verify no unexpected interactions
    verifyNoMoreInteractions(validator, repository, eventPublisher);
}
```

### 7.3.7 Test categories (JUnit tags) — conditional enforcement

Goal: tags improve selectivity (unit/slice/integration/contract) and CI control.
Enforcement strength is repo-dependent (repo-first).

Definitions:

* “Tagging established” is true if at least one applies:
  A) there are existing `@Tag(...)` usages in the repository (more than rare exceptions), OR
  B) the repository’s CI/build uses tags (e.g., Maven Surefire/Failsafe includes/excludes), OR
  C) repository documentation defines tagging as the standard

Rule:

1. If tagging is established:

   * all new AND modified tests must be tagged
   * when touching an existing untagged test, add the tag

2. If tagging is NOT established:

   * all newly created tests must be tagged
   * existing untouched tests must NOT be refactored solely for tagging
   * for modified tests: add the tag if the test is changed anyway

Recommended tag scheme:
`@Tag("unit")` | `@Tag("slice")` | `@Tag("integration")` | `@Tag("contract")`

### 7.3.8 Coverage enforcement

Minimum requirements (automatically verified in Phase 6):

* line coverage: >= 80%
* branch coverage: >= 75%
* mutation coverage: >= 70% (PITest)

Exceptions (must be documented explicitly):

* getters/setters (only if no logic)
* equals/hashCode (if generated by Lombok)
* toString (if generated by Lombok)

### 7.4 Test generation algorithm (for AI)

Step 1: method classification

For each method to test:

1. identify type: Query | Command | State-Transition | External-Call
2. extract parameter types
3. identify possible exceptions (throws clause + `@Valid` annotations)
4. identify side effects (calls to other services/repositories)

Step 2: test matrix generation

For each method type per Chapter 7.3.3:

1. generate HAPPY_PATH test
2. generate NULL_INPUT tests for each parameter
3. if Query: generate NOT_FOUND test
4. if Command: generate CONSTRAINT_VIOLATION tests
5. if State-Transition: generate STATE_INVALID tests
6. if `@PreAuthorize` exists: generate AUTHORIZATION test

Step 3: apply patterns

For each generated test:

1. apply exception pattern (concrete exception + error-code check)
2. apply state-verification pattern (persistence + side effects)
3. use test-data builder (no hardcoded values)
4. add Given/When/Then comments

Step 4: self-review

Before finalizing:

1. verify coverage matrix against checklist
2. scan for anti-patterns
3. mark missing tests as `[INFERENCE-ZONE: Test-Gap]`

Example output for `PersonService.deletePerson(Long id)`:

Note (conditional tagging):

* if tagging is established (or new/modified tests are affected), `@Tag(...)` is mandatory.
* if tagging is NOT established, tagging applies at least to newly created tests; untouched existing tests
  must not be refactored solely for tagging.
  (see Chapter 7.3.7 “Conditional enforcement”.)

```java
// Method-Type: Command (DELETE)
// Expected Tests: HAPPY_PATH, NULL_INPUT, NOT_FOUND, STATE_INVALID, AUTHORIZATION

@Test
@Tag("unit")
void deletePerson_shouldMarkAsDeleted_whenPersonExistsAndNoActiveContracts() {
    // HAPPY_PATH
    // Given
    Person person = aPerson().contracts(emptyList()).build();
    when(repository.findById(person.getId())).thenReturn(Optional.of(person));

    // When
    service.deletePerson(person.getId());

    // Then
    verify(repository).save(argThat(p ->
        p.getId().equals(person.getId()) &&
        p.isDeleted()
    ));
    verify(eventPublisher).publish(any(PersonDeletedEvent.class));
    verifyNoMoreInteractions(repository, eventPublisher);
}

@Test
@Tag("unit")
void deletePerson_shouldThrowException_whenIdIsNull() {
    // NULL_INPUT
    assertThrows(IllegalArgumentException.class,
        () -> service.deletePerson(null));
}

@Test
@Tag("unit")
void deletePerson_shouldThrowNotFoundException_whenPersonDoesNotExist() {
    // NOT_FOUND
    when(repository.findById(999L)).thenReturn(Optional.empty());

    PersonNotFoundException ex = assertThrows(
        PersonNotFoundException.class,
        () -> service.deletePerson(999L)
    );
    assertThat(ex.getCode()).isEqualTo("PERSON_NOT_FOUND");
}

@Test
@Tag("unit")
void deletePerson_shouldThrowBusinessException_whenPersonHasActiveContracts() {
    // STATE_INVALID (CRITICAL!)
    Person person = aPersonWithActiveContracts();
    when(repository.findById(person.getId())).thenReturn(Optional.of(person));

    BusinessException ex = assertThrows(
        BusinessException.class,
        () -> service.deletePerson(person.getId())
    );
    assertThat(ex.getCode()).isEqualTo("ACTIVE_CONTRACTS_EXIST");

    // Verify no changes persisted
    verify(repository, never()).save(any());
    verify(eventPublisher, never()).publish(any());
}

@Test
@Tag("unit")
@WithMockUser(roles = "USER")
void deletePerson_shouldThrowAccessDenied_whenUserNotAuthorized() {
    // AUTHORIZATION (if @PreAuthorize exists)
    Person person = aPerson().ownerId(999L).build();
    when(repository.findById(person.getId())).thenReturn(Optional.of(person));
    when(securityService.isOwner(person.getId())).thenReturn(false);

    assertThrows(AccessDeniedException.class,
        () -> service.deletePerson(person.getId()));
}
```

---

# 8. Evidence & Proof Obligations

All business, architectural, and technical statements by the AI
are subject to a mandatory evidence rule.

There are two explicit evidence modes:

## 8.1 Strict Evidence Mode (Default)

Strict Evidence Mode is the default for all sessions unless explicitly overridden.

Obligations:

* every non-trivial statement MUST be backed by at least one of:

  * `path:line` reference
  * concrete code/config excerpt
* statements without verifiable evidence are NOT allowed
* if evidence is not possible, the AI MUST explicitly say:
  `Not provable with the provided artifacts`

Typical use cases:

* architecture reviews
* implementation and testing phases
* audit/compliance-adjacent contexts

## 8.2 Light Evidence Mode (Explicit exception)

Light Evidence Mode may be used only after explicit approval
(e.g., exploratory analysis, early orientation).

Obligations:

* every statement MUST include at least one:

  * file path OR
  * short relevant code/structure excerpt
* pure speculation remains forbidden
* hallucinations remain disallowed

## 8.3 Rule priority

* evidence mode does not override gates, phases, or scope rules
* confidence levels may never relax evidence obligations

---

# 9. Traceability

Every implementation must be documented in a table:

| Ticket | Classes | Endpoints | Tests | Risks |
| ------ | ------- | --------- | ----- | ----- |

---

# 10. Error, Gaps & Confidence Handling

## 10.1 Handling deficits

* explicitly report missing artifacts (no fabrication)
* mark ambiguities as assumptions and document in session state
* if assumptions materially impact the ticket: ask a clarification

## 10.2 Confidence level & behavior matrix

| Confidence | Mode     | Plan | Code                | Business-rules check  | Behavior                         |
| ---------: | -------- | ---- | ------------------- | --------------------- | -------------------------------- |
|    90–100% | NORMAL   | yes  | yes                 | Phase 1.5 recommended | Full production code             |
|     70–89% | DEGRADED | yes  | yes                 | Phase 1.5 recommended | Warnings + assumptions in output |
|     50–69% | DRAFT    | yes  | only after approval | Phase 1.5 optional    | Plan-only; code only after “Go”  |
|      < 50% | BLOCKED  | yes  | no                  | Phase 1.5 skipped     | Plan sketch + explicit blockers  |

IMPORTANT (gates remain superior):

* regardless of confidence level: production/functional code may only be generated
  if the gates in `master.md` are satisfied (P5=architecture-approved and P5.3=test-quality-pass).
* user approval (“Go”) does not replace gates; at most it complements DRAFT mode.

---

### BuildEvidence impact (binding)

BuildEvidence is the normative distinction between:

* **theoretically correct** (not executed / not proven)
* **verified** (proven by user-provided output/logs)

Rules:

1. If `BuildEvidence.status = not-provided`:

   * statements such as “Build is green”, “Tests pass”, “Coverage is met” are forbidden.
   * the assistant may only state: **“theoretical” / “not verified”**.
   * CONFIDENCE is automatically capped at **85%** (no NORMAL 90–100 possible).

2. If `BuildEvidence.status = partially-provided`:

   * only explicitly proven parts may be considered verified.
   * everything else must be labeled as **theoretical**.
   * CONFIDENCE is automatically capped at **90%**.

3. If `BuildEvidence.status = provided-by-user`:

   * build/test statements may be considered **verified**,
     but only within the scope of provided evidence (command + output/log excerpt).

**Business rules impact on confidence:**

The number of extracted business rules affects the confidence level:

* **0–2 BRs with >50 classes:** confidence -20% (critical gap)
* **3–5 BRs with >50 classes:** confidence -10% (gap likely)
* **6–10 BRs with >50 classes:** confidence +0% (acceptable)
* **10+ BRs with >50 classes:** confidence +10% (well documented)
* **any with <30 classes:** confidence +0% (CRUD project)

**Example:**

```text
Base confidence: 85% (DEGRADED)
Business rules found: 3 for 67 classes
Adjustment: -10%
Final confidence: 75% (DEGRADED with increased risk)
```

### 10.2.1 DRAFT MODE (50–69%)

Without explicit user consent (“Go for DRAFT code”), no functional production code may be produced.
Additionally: code generation is only allowed if the gates in `master.md` are satisfied
(P5=architecture-approved and P5.3=test-quality-pass).
Otherwise, only the plan and risks are shown.

**DRAFT mode with business rules:**

* Phase 1.5 is optional
* if executed: extracted BRs are referenced in the plan
* code generation only after explicit approval
* Phase 5.4 is skipped (because no code is generated)

### 10.2.2 Marking assumptions in code

If code is produced outside NORMAL mode, assumptions must be marked directly in code:

```java
// ASSUMPTION [A1]: description of the assumption (e.g., field type or schema)
```

**Marking missing business rules:**
If business rules exist in the inventory but are missing in code:

```java
public void deletePerson(Long id) {
    Person person = findById(id);

    // INFERENCE-ZONE [BR-001]: Missing check for active contracts
    // Expected: if (!person.getContracts().isEmpty()) throw BusinessException(...)
    // Reason: BR-001 found in inventory but not implemented here

    repository.delete(person);
}
```

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

