# Java Excellence Rulebook

This document defines language-specific excellence standards for Java/Spring Boot.
It is an advisory addon that provides best practices complementing the UserMaxQuality addon.

## Intent (binding)

Enforce Java language excellence through:
- Pattern library for idiomatic Java/Spring
- Anti-pattern catalog with clear reasoning
- Test quality standards specific to Java
- Code quality verification commands

## Scope (binding)

All Java code changes including:
- Spring Boot backend services
- Domain and infrastructure layers
- Test code
- Configuration classes

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
As an advisory addon, this rulebook refines Java behavior and MUST NOT override master/core/profile constraints.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/javaExcellence.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 2: detect Java patterns in codebase, initialize excellence checklist
- Phase 4: apply pattern/anti-pattern checks to changed scope
- Phase 5: verify excellence criteria with evidence refs
- Phase 6: ensure unresolved violations marked with recovery steps

## Evidence contract (binding)

- Maintain `SESSION_STATE.AddonsEvidence.javaExcellence.status` (`loaded|skipped|missing-rulebook`).
- Advisory findings are represented via WARN codes in `warnings[]`; do not hard-block solely from this addon.

## Tooling (binding)

Use repository-native Java tooling for verification:
- Build: `./mvnw verify` or `./gradlew build`
- Format: `./mvnw spotless:check` when Spotless is configured
- Static analysis: `./mvnw checkstyle:check pmd:check spotbugs:check` when configured
- Tests: `./mvnw test` or `./gradlew test`
- Architecture: `./mvnw test -Dtest=*ArchUnitTest` when ArchUnit is present

When tooling is unavailable in host:
- Emit recovery commands
- Mark affected claims as `NOT_VERIFIED`
- Continue conservatively without fabricating evidence

---

## Quality Contract (Binding)

### Required Output Sections (User Mode)

When this addon is active with UserMaxQuality, Java-specific sections enhance the base sections:

1. **Intent & Scope** - Include Java-specific choices (Spring Boot version, reactive vs servlet, ORM choice)
2. **Non-goals** - Include Java features explicitly deferred (e.g., reactive migration, GraalVM native)
3. **Design/Architecture** - Include package structure, layer boundaries, dependency injection strategy
4. **Invariants & Failure Modes** - Include Java-specific failure modes (NPE, lazy loading, transaction boundaries)
5. **Test Plan (Matrix)** - Include test pyramid strategy (unit/slice/integration), mocking approach
6. **Edge Cases Checklist** - Include Java-specific edges (null, empty collections, concurrent access)
7. **Verification Commands** - Include Java-specific commands (Maven/Gradle, tests, static analysis)
8. **Risk Review** - Include Java-specific risks (memory leaks, connection pool exhaustion, thread safety)
9. **Rollback Plan** - Include Java-specific rollback (dependency versions, schema migrations)

### Verification Handshake (Binding)

Inherits from UserMaxQuality. Java-specific verification:

```
LLM Output: "Verification Commands: [mvn verify, mvn test, mvn spotless:check]"
Human Response: "Executed mvn verify: BUILD SUCCESS; Executed mvn test: 127 tests passed; Executed mvn spotless:check: No violations"
LLM: Set `Verified` only after receiving results
```

### Risk-Tier Triggers (Binding)

Java-specific risk surfaces and additional requirements:

| Risk Surface | Trigger Patterns | Additional Requirements |
|--------------|------------------|------------------------|
| Persistence/JPA | `@Entity`, `@Transactional`, `Repository`, JPA queries | NPE audit, lazy-loading audit, transaction boundary review |
| Concurrency | `@Async`, `CompletableFuture`, `synchronized`, `volatile`, `Atomic*` | Thread-safety audit, race condition checklist, deadlock analysis |
| External APIs | `RestTemplate`, `WebClient`, `@FeignClient`, `KafkaTemplate` | Timeout handling, retry logic, circuit breaker review |
| Security | `@PreAuthorize`, `@Secured`, `SecurityConfig`, authentication code | Input validation audit, authorization matrix review |

### Claim Verification (Binding)

Java-specific claim markers:

- **ASSUMPTION(JAVA)**: Java version, Spring Boot version, dependency availability
  - Example: `ASSUMPTION(JAVA): Java 21 for virtual threads support`
  - Example: `ASSUMPTION(JAVA): Spring Boot 3.2 for problem+json auto-config`

- **NOT_VERIFIED(JAVA)**: Java-specific execution not performed
  - Example: `NOT_VERIFIED(JAVA): ArchUnit tests pass (not run)`
  - Example: `NOT_VERIFIED(JAVA): No lazy loading leaks (not verified)`

---

## Pattern Library (Binding)

### PAT-J01: Constructor Injection

**Pattern:** All dependencies injected via constructor; no field or setter injection.

```java
// GOOD
@Service
public class UserService {
    private final UserRepository userRepository;
    private final Clock clock;

    public UserService(UserRepository userRepository, Clock clock) {
        this.userRepository = userRepository;
        this.clock = clock;
    }

    public User createUser(CreateUserCommand command) {
        User user = User.create(command.name(), clock.instant());
        return userRepository.save(user);
    }
}

// BAD - field injection
@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;  // Hidden dependency

    @Autowired
    private Clock clock;  // Cannot be final
}
```

**Why:** Explicit dependencies; enables unit testing without Spring context; `final` fields for immutability.

---

### PAT-J02: Domain-Rich Entities

**Pattern:** Entities contain business logic and enforce invariants, not just getters/setters.

```java
// GOOD - rich domain
@Entity
public class User {
    @Id
    private Long id;
    private String name;
    private Instant createdAt;
    private UserStatus status;

    protected User() {}  // JPA only

    public static User create(String name, Instant createdAt) {
        if (name == null || name.isBlank()) {
            throw new ValidationException("name must not be blank");
        }
        User user = new User();
        user.id = null;  // Generated
        user.name = name;
        user.createdAt = createdAt;
        user.status = UserStatus.ACTIVE;
        return user;
    }

    public void deactivate(String reason) {
        if (this.status == UserStatus.DEACTIVATED) {
            throw new IllegalStateException("User already deactivated");
        }
        this.status = UserStatus.DEACTIVATED;
    }

    public boolean isActive() {
        return this.status == UserStatus.ACTIVE;
    }
}

// BAD - anemic domain
@Entity
@Data  // Only getters/setters
public class User {
    private Long id;
    private String name;
    private Instant createdAt;
    private UserStatus status;
    // No behavior - all logic in service
}
```

**Why:** Invariants enforced at the entity; single source of truth for business rules; testable in isolation.

---

### PAT-J03: DTO Boundary Mapping

**Pattern:** Controllers never expose entities; use DTOs with explicit mapping.

```java
// GOOD
@RestController
@RequestMapping("/users")
public class UserController {
    private final UserService userService;
    private final UserMapper userMapper;

    @PostMapping
    public ResponseEntity<UserResponse> create(@Valid @RequestBody CreateUserRequest request) {
        CreateUserCommand command = userMapper.toCommand(request);
        User user = userService.createUser(command);
        UserResponse response = userMapper.toResponse(user);
        return ResponseEntity.status(201).body(response);
    }
}

@Component
public class UserMapper {
    public CreateUserCommand toCommand(CreateUserRequest request) {
        return new CreateUserCommand(request.name());
    }

    public UserResponse toResponse(User user) {
        return new UserResponse(
            user.getId(),
            user.getName(),
            user.getCreatedAt(),
            user.getStatus()
        );
    }
}

// BAD - entity exposure
@RestController
public class UserController {
    @PostMapping
    public User create(@RequestBody User user) {  // Entity as request/response
        return userRepository.save(user);  // Lazy loading issues, contract coupling
    }
}
```

**Why:** Decouples API contract from persistence; prevents lazy-loading issues; explicit field selection.

---

### PAT-J04: Deterministic Time in Tests

**Pattern:** Production code uses injected `Clock`; tests use fixed time.

```java
// GOOD - production
@Service
public class UserService {
    private final Clock clock;

    public UserService(Clock clock) {
        this.clock = clock;
    }

    public User createUser(String name) {
        return User.create(name, clock.instant());
    }
}

// GOOD - test
class UserServiceTest {
    private static final Instant FIXED_TIME = Instant.parse("2026-01-31T12:00:00Z");
    private static final Clock FIXED_CLOCK = Clock.fixed(FIXED_TIME, ZoneOffset.UTC);

    @Test
    void createUser_setsCreatedAt() {
        var service = new UserService(FIXED_CLOCK, fakeRepository);
        var user = service.createUser("Alice");
        assertThat(user.getCreatedAt()).isEqualTo(FIXED_TIME);
    }
}

// BAD - Instant.now() in production
public User createUser(String name) {
    return User.create(name, Instant.now());  // Untestable
}
```

**Why:** Deterministic tests; reproducible failures; no time-dependent flakiness.

---

### PAT-J05: Explicit Exception Types

**Pattern:** Domain-specific exception hierarchy; never catch bare `Exception`.

```java
// GOOD
public class UserNotFoundException extends RuntimeException {
    public UserNotFoundException(Long userId) {
        super("User not found: " + userId);
    }
}

public class ValidationException extends RuntimeException {
    private final String field;

    public ValidationException(String field, String message) {
        super(message);
        this.field = field;
    }
}

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(UserNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleUserNotFound(UserNotFoundException e) {
        return ResponseEntity.status(404)
            .body(new ErrorResponse("USER_NOT_FOUND", e.getMessage()));
    }

    @ExceptionHandler(ValidationException.class)
    public ResponseEntity<ErrorResponse> handleValidation(ValidationException e) {
        return ResponseEntity.status(400)
            .body(new ErrorResponse("VALIDATION_ERROR", e.getMessage(), e.getField()));
    }
}

// BAD
try {
    // ...
} catch (Exception e) {
    log.error("Error: {}", e.getMessage());  // Swallowed, no recovery
}
```

**Why:** Explicit error handling; proper HTTP status codes; errors are part of the API contract.

---

### PAT-J06: Behavioral Test Assertions

**Pattern:** Tests assert outcomes, not implementation details.

```java
// GOOD - behavioral
class UserServiceTest {
    @Test
    void createUser_withValidInput_persistsUser() {
        var command = new CreateUserCommand("Alice");
        var user = userService.createUser(command);
        assertThat(user.getName()).isEqualTo("Alice");
        assertThat(user.isActive()).isTrue();
        assertThat(fakeRepository.findById(user.getId())).isPresent();
    }

    @Test
    void createUser_withBlankName_throwsValidationException() {
        var command = new CreateUserCommand("");
        assertThatThrownBy(() -> userService.createUser(command))
            .isInstanceOf(ValidationException.class)
            .hasMessageContaining("name must not be blank");
    }
}

// BAD - overspecified
@Test
void createUser_callsRepository() {
    userService.createUser(command);
    verify(userRepository, times(1)).save(any());  // Tests implementation, not behavior
}
```

**Why:** Tests survive refactoring; verify actual requirements, not implementation choices.

---

## Anti-Pattern Catalog (Binding)

### AP-J-EXCEL-01: Fat Controller

**Pattern:** Business logic in controller methods.

**Detection:** `if`/`switch` statements in controllers branching on domain state.

**Recovery:** Extract to service layer; controller only maps request → command, calls service, maps response.

---

### AP-J-EXCEL-02: Anemic Domain

**Pattern:** Entities with only getters/setters; all logic in services.

**Detection:** Entity classes with no business methods; services with validation that belongs in entities.

**Recovery:** Move invariants and behavior to entities; services orchestrate use cases only.

---

### AP-J-EXCEL-03: Entity Exposure

**Pattern:** Controllers returning JPA entities or accepting entities as request bodies.

**Detection:** Controller return types that are `@Entity` classes.

**Recovery:** Create DTO classes; use mapper to convert between entity and DTO.

---

### AP-J-EXCEL-04: Field Injection

**Pattern:** `@Autowired` on fields instead of constructors.

**Detection:** `@Autowired` annotations on fields (not constructors).

**Recovery:** Convert to constructor injection; make fields `final`.

---

### AP-J-EXCEL-05: Swallowed Exceptions

**Pattern:** `catch (Exception e)` blocks that only log without rethrowing or returning error.

**Detection:** Catch blocks with only `log.error(...)` and no throw/return.

**Recovery:** Rethrow as domain exception; return error response; or use `@ControllerAdvice`.

---

### AP-J-EXCEL-06: God Service

**Pattern:** Service class with 10+ methods or 5+ dependencies.

**Detection:** Service classes with many public methods; excessive constructor parameters.

**Recovery:** Split by use case or domain concept; each service handles one responsibility.

---

### AP-J-EXCEL-07: Nondeterministic Tests

**Pattern:** Tests using `Instant.now()`, `Thread.sleep()`, `UUID.randomUUID()` without injection.

**Detection:** Direct calls to time/random APIs in test code.

**Recovery:** Inject `Clock` for time; use fixed IDs; use Awaitility for async.

---

### AP-J-EXCEL-08: Transaction Boundary Leak

**Pattern:** External HTTP/messaging calls inside `@Transactional` methods.

**Detection:** `@Transactional` methods calling `RestTemplate`, `WebClient`, `KafkaTemplate`.

**Recovery:** Move external calls outside transaction; use saga pattern if needed.

---

### AP-J-EXCEL-09: Test Overspecification

**Pattern:** Tests using `verify(mock, times(n))` without behavioral assertions.

**Detection:** Heavy Mockito `verify()` usage; no outcome assertions.

**Recovery:** Assert actual results and state changes; remove internal call verification.

---

### AP-J-EXCEL-10: Mutable Domain

**Pattern:** `@Data` on entities; public setters used throughout codebase.

**Detection:** Lombok `@Data` on entities; scattered `entity.setXxx()` calls.

**Recovery:** Remove setters; add domain methods for state changes; use `@Getter` only.

---

## Verification Commands (Binding)

When this addon is active, verify Java excellence with:

```bash
# Build and test
./mvnw verify

# Format check (if Spotless configured)
./mvnw spotless:check

# Static analysis (if configured)
./mvnw checkstyle:check
./mvnw pmd:check
./mvnw spotbugs:check

# Architecture tests (if ArchUnit present)
./mvnw test -Dtest=*ArchUnitTest

# Dependency analysis
./mvnw dependency:analyze
```

---

## Warning Codes (Binding)

- `WARN-JAVA-EXCEL-CONSTRUCTOR-INJECTION`: Field or setter injection detected
- `WARN-JAVA-EXCEL-ENTITY-EXPOSURE`: Controller returns entity type
- `WARN-JAVA-EXCEL-SWALLOWED-EXCEPTION`: Catch block without rethrow/recovery
- `WARN-JAVA-EXCEL-NONDETERMINISTIC-TEST`: Test uses Instant.now()/Thread.sleep() without seam
- `WARN-JAVA-EXCEL-GOD-SERVICE`: Service exceeds method/dependency threshold
- `WARN-JAVA-EXCEL-TRANSACTION-LEAK`: External call inside transaction

---

## Shared Principal Governance Contracts (Binding)

This addon delegates to shared governance contracts:

- `rules.principal-excellence.md` - Principal-grade review criteria
- `rules.risk-tiering.md` - Risk tier classification
- `rules.scorecard-calibration.md` - Scorecard evaluation

Tracking keys (audit pointers, not activation logic):
- `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
- `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
- `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`

---

## Examples (GOOD/BAD)

### GOOD: Complete Java Excellence

```java
// domain/User.java - rich domain
@Entity
public class User {
    @Id @GeneratedValue
    private Long id;
    private String name;
    private Instant createdAt;
    private UserStatus status;

    protected User() {}

    public static User create(String name, Instant createdAt) {
        if (name == null || name.isBlank()) {
            throw new ValidationException("name", "must not be blank");
        }
        var user = new User();
        user.name = name;
        user.createdAt = createdAt;
        user.status = UserStatus.ACTIVE;
        return user;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public Instant getCreatedAt() { return createdAt; }
    public boolean isActive() { return status == UserStatus.ACTIVE; }
}

// service/UserService.java - constructor injection
@Service
public class UserService {
    private final UserRepository repository;
    private final Clock clock;

    public UserService(UserRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public User createUser(CreateUserCommand command) {
        var user = User.create(command.name(), clock.instant());
        return repository.save(user);
    }
}

// test/UserServiceTest.java - deterministic, behavioral
class UserServiceTest {
    static final Instant FIXED_TIME = Instant.parse("2026-01-31T12:00:00Z");
    static final Clock FIXED_CLOCK = Clock.fixed(FIXED_TIME, ZoneOffset.UTC);

    @Test
    void createUser_withValidInput_persistsUser() {
        var repo = new InMemoryUserRepository();
        var service = new UserService(repo, FIXED_CLOCK);

        var user = service.createUser(new CreateUserCommand("Alice"));

        assertThat(user.getName()).isEqualTo("Alice");
        assertThat(user.getCreatedAt()).isEqualTo(FIXED_TIME);
        assertThat(user.isActive()).isTrue();
    }
}
```

### BAD: Multiple Violations

```java
// Violations: field injection, anemic domain, entity exposure, nondeterministic
@Service
public class UserService {
    @Autowired
    private UserRepository repository;  // Field injection

    public UserEntity create(String name) {  // Returns entity
        var entity = new UserEntity();  // Anemic - no validation
        entity.setName(name);
        entity.setCreatedAt(Instant.now());  // Nondeterministic
        return repository.save(entity);
    }
}

@RestController
public class UserController {
    @PostMapping
    public UserEntity create(@RequestBody UserEntity entity) {  // Entity as request/response
        return service.create(entity.getName());
    }
}
```

---

## Troubleshooting

1) Symptom: WARN-JAVA-EXCEL-CONSTRUCTOR-INJECTION
- Cause: `@Autowired` on field instead of constructor
- Fix: Convert to constructor injection; remove `@Autowired` from fields

2) Symptom: WARN-JAVA-EXCEL-ENTITY-EXPOSURE
- Cause: Controller returns `@Entity` type
- Fix: Create DTO class; add mapper; return DTO from controller

3) Symptom: WARN-JAVA-EXCEL-NONDETERMINISTIC-TEST
- Cause: Test uses `Instant.now()` or `Thread.sleep()`
- Fix: Inject `Clock` and use fixed instant; use Awaitility for async

4) Symptom: WARN-JAVA-EXCEL-TRANSACTION-LEAK
- Cause: External call inside `@Transactional` method
- Fix: Move external call outside transaction or use saga pattern

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
