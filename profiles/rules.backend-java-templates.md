# Backend Java - LLM Code & Test Templates (ADDON)

**Purpose (binding):** Provide concrete copy-paste templates so the assistant generates deterministic, reviewable backend-java code and tests.

**Addon class (binding):** required addon.

**Activation (binding):** MUST be loaded at code-phase (Phase 4+) when `SESSION_STATE.ActiveProfile = "backend-java"`.
- If SESSION_STATE.Phase is in code-phase set (Phase 4+) and this addon is not loaded: Mode = BLOCKED, Next = BLOCKED-MISSING-TEMPLATES.

**Precedence (binding):** `master.md` > `rules.md` (core) > this addon > `rules.backend-java.md` (profile).
- In conflicts, this addon’s templates override abstract style/principles.

---

## 14. LLM CODE GENERATION PATTERNS (Binding)

### Core Principle

LLMs are **pattern matchers**, not abstract reasoners.

- ❌ **Abstract rule:** "Controllers should delegate to services"
  → LLM generates 10 different variations (inconsistent)

- ✅ **Concrete template:** `User result = service.create(domain);`
  → LLM copies exact structure (consistent, correct)

**Rule (Binding):**
When generating code, the assistant MUST follow the templates in this section as the default structure, substituting placeholders marked with `{...}`.

If a template conflicts with repository-established conventions (locked in `SESSION_STATE`), the assistant MUST:
- keep the same architectural intent,
- apply the minimal convention-aligned adaptation,
- and record the deviation briefly in the plan/evidence.

---

### 14.1 Controller Pattern (REST API Endpoint)

**Template for POST (Create):**

```java
@RestController
@RequestMapping("/api/{resources}")
@RequiredArgsConstructor
public class {Resource}Controller {
    
    private final {Resource}Service service;
    private final {Resource}Mapper mapper;
    
    @PostMapping
    public ResponseEntity<{Resource}Response> create(
        @Valid @RequestBody {Resource}CreateRequest request
    ) {
        // 1. Map to domain
        {Resource} domain = mapper.toDomain(request);
        
        // 2. Delegate (single line, no logic here)
        {Resource} result = service.create(domain);
        
        // 3. Map to response
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(mapper.toResponse(result));
    }
}
```

**Template for GET (Read by ID):**

```java
@GetMapping("/{id}")
public ResponseEntity<{Resource}Response> getById(@PathVariable Long id) {
    {Resource} result = service.findById(id)
        .orElseThrow(() -> new {Resource}NotFoundException(id));
    
    return ResponseEntity.ok(mapper.toResponse(result));
}
```

**Template for PUT (Update):**

```java
@PutMapping("/{id}")
public ResponseEntity<{Resource}Response> update(
    @PathVariable Long id,
    @Valid @RequestBody {Resource}UpdateRequest request
) {
    {Resource} domain = mapper.toDomain(request);

    {Resource} result = service.update(id, domain);
    
    return ResponseEntity.ok(mapper.toResponse(result));
}
```

**Template for DELETE:**

```java
@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(@PathVariable Long id) {
    service.delete(id);
    return ResponseEntity.noContent().build();
}
```

**Binding Rules:**
- Controllers MUST have `@RequiredArgsConstructor` (constructor injection)
- Controllers MUST NOT contain business logic (no `if` for business rules)
- Controllers MUST delegate to service in **single line**
- Controllers MUST use mapper for DTO ↔ Domain conversion

---

### 14.2 Service Pattern (Use Case / Business Logic)

**Template for Service:**

```java
@Service
@RequiredArgsConstructor
@Transactional
public class {Resource}Service {
    
    private final {Resource}Repository repository;
    private final Clock clock;  // ALWAYS inject Clock for timestamps
    
    public {Resource} create({Resource} {resource}) {
        // 1. Validate (delegate to entity if possible)
        {resource}.validate();
        
        // 2. Set timestamps
        Instant now = clock.instant();
        {resource}.setCreatedAt(now);
        {resource}.setUpdatedAt(now);
        
        // 3. Persist
        return repository.save({resource});
    }
    
    @Transactional(readOnly = true)
    public Optional<{Resource}> findById(Long id) {
        return repository.findById(id);
    }
    
    public {Resource} update(Long id, {Resource} {resource}) {
        // 1. Check exists
        {Resource} existing = repository.findById(id)
            .orElseThrow(() -> new {Resource}NotFoundException(id));
        
        // 2. Business logic (prefer entity methods)
        existing.update({resource}, clock.instant());
        
        // 3. Persist
        return repository.save(existing);
    }
    
    @Transactional
    public void delete(Long id) {
        {Resource} existing = repository.findById(id)
            .orElseThrow(() -> new {Resource}NotFoundException(id));
        
        // Business logic (prefer entity methods)
        existing.validateCanBeDeleted();
        
        repository.delete(existing);
    }
}
```

**Binding Rules:**
- Services MUST have `@Transactional` at class level
- Services MUST inject `Clock` (never use `Instant.now()` directly)
- Services SHOULD delegate business logic to entity methods
- Services coordinate **orchestration** (call multiple repos/entities)

---

### 14.3 Entity Pattern (Rich Domain Model)

**Template for Entity:**

```java
@Entity
@Table(name = "{resources}")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
@Builder(toBuilder = true)
public class {Resource} {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(nullable = false, length = 100)
    private String name;
    
    @Column(nullable = false)
    private Instant createdAt;
    
    @Column(nullable = false)
    private Instant updatedAt;
    
    @Version
    private Long version;  // Optimistic locking
    
    // Business logic IN the entity (Rich Domain Model)
    
    public void validate() {
        if (name == null || name.isBlank()) {
            throw new ValidationException("Name is required");
        }
        if (name.length() > 100) {
            throw new ValidationException("Name too long");
        }
    }
    
    public void update({Resource} updated, Instant now) {
        this.name = updated.getName();
        this.updatedAt = now;
    }
    
    public void validateCanBeDeleted() {
        // Example: check invariants
        // if (hasActiveContracts()) {
        //     throw new BusinessException("Cannot delete: active contracts");
        // }
    }
}
```

**Binding Rules:**
- Entities SHOULD use `@Version` (optimistic locking); if repo conventions intentionally avoid it, preserve repo style and document concurrency handling explicitly.
- Entities MUST enforce invariants in domain methods OR in an explicit domain service (repo pattern), but never in controllers.
- Entities MUST NOT have setters for business-critical fields (use methods)
- Timestamps MUST be `Instant` (not LocalDateTime)
- Use Lombok: `@Getter`, `@Builder(toBuilder = true)`, `@NoArgsConstructor(protected)`

---

### 14.4 Exception Handling Pattern

**Template for Custom Exception:**

```java
public class {Resource}NotFoundException extends RuntimeException {
    public {Resource}NotFoundException(Long id) {
        super("Resource not found: " + id);
    }
}
```

**Template for GlobalExceptionHandler:**

```java
@RestControllerAdvice
@RequiredArgsConstructor
public class GlobalExceptionHandler {
    private final Clock clock;

    @ExceptionHandler({Resource}NotFoundException.class)
    public ResponseEntity<ErrorResponse> handle{Resource}NotFound(
        {Resource}NotFoundException ex,
        WebRequest request
    ) {
        ErrorResponse error = ErrorResponse.builder()
            .status(HttpStatus.NOT_FOUND.value())
            .message(ex.getMessage())
            .code("{RESOURCE}_NOT_FOUND")
            .timestamp(clock.instant())
            .path(extractPath(request))
            .build();
        
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error);
    }
    
    @ExceptionHandler(ValidationException.class)
    public ResponseEntity<ErrorResponse> handleValidation(
        ValidationException ex,
        WebRequest request
    ) {
        ErrorResponse error = ErrorResponse.builder()
            .status(HttpStatus.BAD_REQUEST.value())
            .message(ex.getMessage())
            .code("VALIDATION_FAILED")
            .timestamp(clock.instant())
            .path(extractPath(request))
            .build();
        
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(error);
    }
    
    private String extractPath(WebRequest request) {
        return ((ServletWebRequest) request).getRequest().getRequestURI();
    }
}
```

**Binding Rules:**
- Exception handlers MUST use `@RestControllerAdvice`
- Error responses MUST have stable error codes
- Error responses SHOULD include timestamp and path

Controller tests MUST NOT assert timestamp unless Clock is controlled/mocked.

---

### 14.5 Placeholder Substitution Rules (Binding)

When using templates above, substitute:

| Placeholder | Substitution | Example |
|------------|--------------|---------|
| `{Resource}` | Entity name (singular, PascalCase) | `User`, `Order`, `Product` |
| `{resource}` | Entity name (singular, camelCase) | `user`, `order`, `product` |
| `{resources}` | Entity name (plural, lowercase) | `users`, `orders`, `products` |
| `{RESOURCE}` | Entity name (singular, UPPER_SNAKE) | `USER`, `ORDER`, `PRODUCT` |

Placeholders must be substituted in class names, method names, annotations, and string literals (e.g., request mappings).

**Examples:**
- Template: `{Resource}Service`
- Substituted: `UserService`, `OrderService`

---

## 15. LLM TEST GENERATION PATTERNS (Binding)

### Core Principle

Tests are HARDER for LLMs than business code. Without templates:
- ❌ Flaky (uses `Instant.now()`)
- ❌ Overspecified (tests implementation, not behavior)
- ❌ Inconsistent (different styles every ticket)

With templates:
- ✅ Deterministic (fixed time, seeded random)
- ✅ Behavior-focused (tests outcomes, not internals)
- ✅ Consistent (always same structure)

---

### 15.1 Test Data Builder Pattern (ALWAYS use)

**Template for Test Data Builder:**

```java
public class {Resource}TestDataBuilder {
    
    private static final Instant FIXED_TIME = 
        Instant.parse("2026-01-31T10:00:00Z");
    
    public static {Resource} given{Resource}() {
        return {Resource}.builder()
            .id(1L)
            .name("Test {Resource}")
            .createdAt(FIXED_TIME)
            .updatedAt(FIXED_TIME)
            .version(1L)
            .build();
    }
    
    public static {Resource}CreateRequest given{Resource}CreateRequest() {
        return {Resource}CreateRequest.builder()
            .name("Test {Resource}")
            .build();
    }
    
    public static {Resource}Response given{Resource}Response() {
        return {Resource}Response.builder()
            .id(1L)
            .name("Test {Resource}")
            .createdAt(FIXED_TIME)
            .build();
    }
}
```

**Binding Rules:**
- ALWAYS use builders (never `new {Resource}()`)
- ALWAYS use `FIXED_TIME` (never `Instant.now()`)
- ALWAYS use `static` factory methods (`given{Resource}()`)
- Test data builders MUST be in `src/test/java` (same package as entity)

---

### 15.2 Service Unit Test Template

**Template for Service Test:**

```java
@ExtendWith(MockitoExtension.class)
@DisplayName("{Resource}Service")
class {Resource}ServiceTest {
    
    @InjectMocks
    private {Resource}Service service;
    
    @Mock
    private {Resource}Repository repository;
    
    @Mock
    private Clock clock;
    
    private static final Instant FIXED_TIME = 
        Instant.parse("2026-01-31T10:00:00Z");
    
    @BeforeEach
    void setUp() {
        when(clock.instant()).thenReturn(FIXED_TIME);
    }
    
    @Nested
    @DisplayName("create()")
    class Create {
        
        @Test
        @DisplayName("should persist {resource} with timestamps")
        void create_withValidInput_persists{Resource}WithTimestamps() {
            // GIVEN
            {Resource} input = given{Resource}()
                .toBuilder()
                .id(null)
                .createdAt(null)
                .updatedAt(null)
                .build();
            
            when(repository.save(any({Resource}.class)))
                .thenAnswer(inv -> inv.getArgument(0));
            
            // WHEN
            {Resource} result = service.create(input);
            
            // THEN
            assertThat(result.getCreatedAt()).isEqualTo(FIXED_TIME);
            assertThat(result.getUpdatedAt()).isEqualTo(FIXED_TIME);
            
            verify(repository).save(argThat({resource} ->
                {resource}.getCreatedAt().equals(FIXED_TIME) &&
                {resource}.getUpdatedAt().equals(FIXED_TIME)
            ));
        }
        
        @Test
        @DisplayName("should throw exception when validation fails")
        void create_withInvalidInput_throwsValidationException() {
            // GIVEN
            {Resource} invalid = given{Resource}()
                .toBuilder()
                .name(null)
                .build();
            
            // WHEN / THEN
            assertThatThrownBy(() -> service.create(invalid))
                .isInstanceOf(ValidationException.class)
                .hasMessageContaining("Name is required");
        }
    }
    
    @Nested
    @DisplayName("findById()")
    class FindById {
        
        @Test
        @DisplayName("should return {resource} when exists")
        void findById_whenExists_returns{Resource}() {
            // GIVEN
            Long id = 1L;
            {Resource} existing = given{Resource}();
            when(repository.findById(id)).thenReturn(Optional.of(existing));
            
            // WHEN
            Optional<{Resource}> result = service.findById(id);
            
            // THEN
            assertThat(result).isPresent();
            assertThat(result.get()).isEqualTo(existing);
        }
        
        @Test
        @DisplayName("should return empty when not exists")
        void findById_whenNotExists_returnsEmpty() {
            // GIVEN
            Long id = 999L;
            when(repository.findById(id)).thenReturn(Optional.empty());
            
            // WHEN
            Optional<{Resource}> result = service.findById(id);
            
            // THEN
            assertThat(result).isEmpty();
        }
    }
}
```

**Binding Rules:**
- Test classes MUST use `@ExtendWith(MockitoExtension.class)`
- Test classes MUST use `@DisplayName` (clear intent)
- Test methods MUST follow pattern: `methodName_condition_expectedOutcome`
- Test methods MUST use `@DisplayName` (natural language)
- Test methods MUST use Given/When/Then comments
- Test methods MUST use AssertJ (`assertThat`)
- Test methods MUST use `@Nested` classes for grouping by method
- Clock MUST be mocked with `FIXED_TIME`

---

### 15.3 Controller Integration Test Template

**Template for Controller Integration Test:**

```java
@WebMvcTest({Resource}Controller.class)
@DisplayName("{Resource}Controller")
class {Resource}ControllerTest {
    
    @Autowired
    private MockMvc mockMvc;
    
    @MockBean
    private {Resource}Service service;
    
    @MockBean
    private {Resource}Mapper mapper;
    
    private ObjectMapper objectMapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
    
    @Nested
    @DisplayName("POST /api/{resources}")
    class Create {
        
        @Test
        @DisplayName("should return 201 with created {resource}")
        void create_withValidRequest_returns201() throws Exception {
            // GIVEN
            {Resource}CreateRequest request = given{Resource}CreateRequest();
            {Resource} domain = given{Resource}();
            {Resource}Response response = given{Resource}Response();
            
            when(mapper.toDomain(request)).thenReturn(domain);
            when(service.create(domain)).thenReturn(domain);
            when(mapper.toResponse(domain)).thenReturn(response);
            
            // WHEN / THEN
            mockMvc.perform(post("/api/{resources}")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Test {Resource}"));
        }
        
        @Test
        @DisplayName("should return 400 when name is null")
        void create_withNullName_returns400() throws Exception {
            // GIVEN
            {Resource}CreateRequest invalid = {Resource}CreateRequest.builder()
                .name(null)
                .build();
            
            // WHEN / THEN
            mockMvc.perform(post("/api/{resources}")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(invalid)))
                .andExpect(status().isBadRequest());
        }
    }
    
    @Nested
    @DisplayName("GET /api/{resources}/{id}")
    class GetById {
        
        @Test
        @DisplayName("should return 200 with {resource}")
        void getById_whenExists_returns200() throws Exception {
            // GIVEN
            Long id = 1L;
            {Resource} domain = given{Resource}();
            {Resource}Response response = given{Resource}Response();
            
            when(service.findById(id)).thenReturn(Optional.of(domain));
            when(mapper.toResponse(domain)).thenReturn(response);
            
            // WHEN / THEN
            mockMvc.perform(get("/api/{resources}/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Test {Resource}"));
        }
        
        @Test
        @DisplayName("should return 404 when not exists")
        void getById_whenNotExists_returns404() throws Exception {
            // GIVEN
            Long id = 999L;
            when(service.findById(id)).thenReturn(Optional.empty());
            
            // WHEN / THEN
            mockMvc.perform(get("/api/{resources}/{id}", id))
                .andExpect(status().isNotFound());
        }
    }
}
```

**Binding Rules:**
- Controller tests MUST use `@WebMvcTest({Resource}Controller.class)`
- Controller tests MUST use MockMvc
- Controller tests MUST test HTTP contract (status codes, JSON paths)
- Controller tests MUST mock service + mapper
- Controller tests MUST validate error cases (400, 404, etc.)

---

### 15.4 Repository Test Template

**Template for Repository Test:**

```java
@DataJpaTest
@DisplayName("{Resource}Repository")
class {Resource}RepositoryTest {
    
    @Autowired
    private {Resource}Repository repository;
    
    @Autowired
    private TestEntityManager entityManager;
    
    @Test
    @DisplayName("should persist and retrieve {resource}")
    void save_withValid{Resource}_persistsAndRetrieves() {
        // GIVEN
        {Resource} {resource} = given{Resource}()
            .toBuilder()
            .id(null)
            .build();
        
        // WHEN
        {Resource} saved = repository.save({resource});
        entityManager.flush();
        entityManager.clear();
        
        // THEN
        {Resource} found = repository.findById(saved.getId()).orElseThrow();
        assertThat(found.getName()).isEqualTo({resource}.getName());
        assertThat(found.getVersion()).isEqualTo(1L);
    }
    
    @Test
    @DisplayName("should enforce unique constraint on name")
    void save_withDuplicateName_throwsException() {
        // GIVEN
        {Resource} first = given{Resource}()
            .toBuilder()
            .id(null)
            .name("Duplicate")
            .build();
        repository.save(first);
        entityManager.flush();
        
        {Resource} second = given{Resource}()
            .toBuilder()
            .id(null)
            .name("Duplicate")
            .build();
        
        // WHEN / THEN
        assertThatThrownBy(() -> {
            repository.save(second);
            entityManager.flush();
        }).isInstanceOf(DataIntegrityViolationException.class);
    }
}
```

**Binding Rules:**
- Repository tests MUST use `@DataJpaTest`
- Repository tests MUST use TestEntityManager
- Repository tests MUST test constraints (unique, nullable, etc.)
- Repository tests MUST flush + clear before assertions

---

## 16. BUSINESS LOGIC PLACEMENT GUIDE (Binding)

### 16.1 Decision Tree: WHERE to place business logic?

```
QUESTION: Where should I put this business logic?

START
  ↓
IS logic specific to ONE entity/aggregate?
  ├─ YES → Entity method (Rich Domain Model)
  │         Example: Person.canBeDeleted()
  │         Example: Order.calculateTotal()
  │         Example: User.activate()
  │
  └─ NO ┐
        ↓
        IS logic a PURE FUNCTION (no state, no side-effects)?
        ├─ YES → Static utility / Domain Service
        │         Example: PriceCalculator.calculate(items)
        │         Example: TaxCalculator.calculate(amount, region)
        │
        └─ NO ┐
              ↓
              DOES logic orchestrate MULTIPLE aggregates?
              ├─ YES → Application Service (use case)
              │         Example: OrderService.checkout(order, payment)
              │         Example: UserService.transferOwnership(from, to)
              │
              └─ NO → ASK USER
                      (unclear responsibility)
```

**Binding Rule:**
When generating code, the assistant MUST follow this decision tree and document the decision in the response.

---

### 16.2 Examples: Correct vs. Wrong

#### Example 1: Can user be deleted?

**❌ WRONG (Service has the logic):**

```java
@Service
public class UserService {
    public void delete(Long id) {
        User user = repository.findById(id).orElseThrow();
        
        // ❌ Business logic in service
        if (!user.getContracts().isEmpty()) {
            throw new BusinessException("User has active contracts");
        }
        
        repository.delete(user);
    }
}
```

**✅ CORRECT (Entity has the logic):**

```java
@Entity
public class User {
    // ...
    
    // ✅ Business logic in entity
    public void validateCanBeDeleted() {
        if (!contracts.isEmpty()) {
            throw new BusinessException("User has active contracts");
        }
    }
}

@Service
public class UserService {
    public void delete(Long id) {
        User user = repository.findById(id).orElseThrow();
        user.validateCanBeDeleted();  // ✅ Delegate to entity
        repository.delete(user);
    }
}
```

---

#### Example 2: Calculate order total

**❌ WRONG (Controller has the logic):**

```java
@RestController
public class OrderController {
    @PostMapping("/orders/{id}/total")
    public ResponseEntity<TotalResponse> calculateTotal(@PathVariable Long id) {
        Order order = service.findById(id);
        
        // ❌ Business logic in controller
        double total = 0;
        for (OrderItem item : order.getItems()) {
            total += item.getPrice() * item.getQuantity();
        }
        
        return ResponseEntity.ok(new TotalResponse(total));
    }
}
```

**✅ CORRECT (Entity has the logic):**

```java
@Entity
public class Order {
    // ...
    
    // ✅ Business logic in entity
    public Money calculateTotal() {
        return items.stream()
            .map(OrderItem::getLineTotal)
            .reduce(Money.ZERO, Money::add);
    }
}

@RestController
public class OrderController {
    @PostMapping("/orders/{id}/total")
    public ResponseEntity<TotalResponse> calculateTotal(@PathVariable Long id) {
        Order order = service.findById(id);
        Money total = order.calculateTotal();  // ✅ Delegate to entity
        return ResponseEntity.ok(mapper.toTotalResponse(total));
    }
}
```

---

#### Example 3: Transfer ownership (multiple aggregates)

**✅ CORRECT (Service orchestrates):**

```java
@Service
public class UserService {
    @Transactional
    public void transferOwnership(Long fromUserId, Long toUserId) {
        // ✅ Service orchestrates multiple aggregates
        User fromUser = repository.findById(fromUserId).orElseThrow();
        User toUser = repository.findById(toUserId).orElseThrow();
        
        // Validation on entities
        fromUser.validateCanTransferOwnership();
        toUser.validateCanReceiveOwnership();
        
        // Orchestration in service
        List<Resource> resources = resourceRepository.findByOwnerId(fromUserId);
        resources.forEach(resource -> resource.setOwner(toUser));
        
        resourceRepository.saveAll(resources);
    }
}
```

---

### 16.3 Quick Reference Table

| Logic Type | Location | Example |
|-----------|----------|---------|
| Single entity validation | Entity method | `user.validate()` |
| Single entity calculation | Entity method | `order.calculateTotal()` |
| Single entity state change | Entity method | `user.activate()` |
| Pure function (no state) | Static utility | `TaxCalculator.calculate()` |
| Multi-aggregate orchestration | Service | `OrderService.checkout()` |
| External system call | Service | `PaymentService.charge()` |
| HTTP/validation/mapping | Controller | `@Valid @RequestBody` |

---

## 17. INTEGRATION CHECKLIST

To ensure LLMs generate optimal code, verify:

### Code Generation
- ✅ Controller follows template (Section 14.1)
- ✅ Service follows template (Section 14.2)
- ✅ Entity follows template (Section 14.3)
- ✅ Exception handling follows template (Section 14.4)
- ✅ Placeholders substituted correctly (Section 14.5)

### Test Generation
- ✅ Test data builders used (Section 15.1)
- ✅ Service tests follow template (Section 15.2)
- ✅ Controller tests follow template (Section 15.3)
- ✅ Repository tests follow template (Section 15.4)

### Architecture
- ✅ Business logic placement correct (Section 16.1 decision tree)
- ✅ No logic in controllers (only delegate)
- ✅ Clock injected (no `Instant.now()`)
- ✅ Tests deterministic (`FIXED_TIME`)

---

## 18. APPENDIX: WHY TEMPLATES MATTER

### LLM Behavior Analysis

**Without Templates (Abstract Rules):**
```
Prompt: "Create a REST endpoint for User creation"

LLM reads: "Controllers should validate and delegate"

LLM generates:
- Variation 1: Manual validation in controller
- Variation 2: Service validates
- Variation 3: Entity validates
→ Inconsistent (different every ticket)
```

**With Templates (Concrete Patterns):**
```
Prompt: "Create a REST endpoint for User creation"

LLM reads: Template 14.1 (Controller Pattern)

LLM generates:
- Always: @Valid @RequestBody UserCreateRequest
- Always: mapper.toDomain(request)
- Always: service.create(domain)
→ Consistent (same every ticket)
```

---

**END OF TEMPLATE ADDON**

---
## Java-first Principal Hardening v2 - Template Conformance (Binding)

### JTH2-1 Template conformance gate (binding)

For generated Java business/test code, the workflow MUST verify and record conformance against Sections 14-17.

Minimum conformance checks for changed scope:

- Controller delegates in one line (no business branching in controller)
- Service orchestrates use case and uses deterministic seams for time
- Entity/domain logic placement follows Section 16 decision tree
- Tests use deterministic setup (`FIXED_TIME` or repo equivalent) and assert behavior over internals

If any conformance item fails, principal completion cannot be declared.

### JTH2-2 Evidence artifact contract (binding)

When templates are used, BuildEvidence MUST include references for:

- `EV-TPL-CODE`: code conformance evidence (path + snippet references)
- `EV-TPL-TEST`: test conformance evidence (path + test names)
- `EV-TPL-GATE`: gate decision evidence (pass/fail with rationale)

Claims without these evidence refs MUST be marked `not-verified`.

### JTH2-3 High-risk template extensions (binding)

When touched scope includes persistence, security, or async messaging, template usage alone is not sufficient.
The workflow MUST add risk-specific checks and tests (constraints, auth/error semantics, idempotency/retry behavior).

### JTH2-4 Template deviation protocol (binding)

If repo conventions require deviation from templates, record:

- deviation reason
- preserved architectural intent
- risk impact (`low` | `medium` | `high`)
- compensating test added

Without deviation record, gate result cannot be `pass`.

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
