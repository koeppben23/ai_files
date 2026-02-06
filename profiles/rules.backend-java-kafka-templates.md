# Backend Java - Kafka Code & Test Templates (ADDON)

**Purpose (binding):** Provide concrete copy-paste templates so the assistant generates deterministic, reviewable Kafka producers/consumers and tests in backend-java repos.

**Addon class (binding):** required addon.

**Activation (binding):** MUST be loaded at code-phase (Phase 4+) when Kafka is required (see `rules.backend-java.md`).
- If Kafka is required and this addon is not loaded: `Mode = BLOCKED`, `Next = BLOCKED-KAFKA-TEMPLATES-MISSING`.

**Precedence (binding):** `master.md` > `rules.md` (core) > this Kafka addon > `rules.backend-java-templates.md` (base templates) > `rules.backend-java.md` (profile).
- In conflicts for Kafka-related code, this addon overrides abstract style/principles.

---

## K1. LLM KAFKA CODE GENERATION PATTERNS (Binding)

**Rule (Binding):**
When generating Kafka code, the assistant MUST follow the templates in this file as the default structure, substituting placeholders marked with `{...}`.
If a template conflicts with locked repo conventions, apply the minimal convention-aligned adaptation and record the deviation.

### K1.1 Placeholder Substitution Rules (Binding)

| Placeholder | Substitution | Example |
|------------|--------------|---------|
| `{Topic}` | Kafka topic name (lowercase, dot or hyphen separated) | `person.created`, `person.updated` |
| `{Event}` | Event name (PascalCase) | `PersonCreatedEvent` |
| `{event}` | event name (camelCase) | `personCreatedEvent` |
| `{Key}` | domain identity used as message key | `PersonId` |
| `{GroupId}` | consumer group id | `personmanagement.person-events` |
| `{Producer}` | producer service name | `PersonEventProducer` |
| `{Consumer}` | consumer class name | `PersonEventConsumer` |
| `{Resource}` | domain aggregate name (PascalCase) | `Person` |

Placeholders must be substituted in class names, method names, annotations, and string literals (e.g., topic names).

---

## K2. Producer Template (Binding)

### K2.1 Producer Service (KafkaTemplate)

```java
@Service
@RequiredArgsConstructor
public class {Producer} {

    private final KafkaTemplate<String, {Event}> kafkaTemplate;
    private final Clock clock;

    public void publish({Event} {event}) {
        // Deterministic timestamp (if the event has one)
        Instant now = clock.instant();

        // If your event supports it, set timestamp deterministically (optional pattern)
        // {event}.setOccurredAt(now);

        kafkaTemplate.send(
            "{Topic}",
            String.valueOf({event}.get{Key}()),
            {event}
        );
    }
}
```

**Binding Rules:**
- Producers MUST be `@Service` and constructor-injected (`@RequiredArgsConstructor`).
- Producers MUST NOT contain business logic (they only publish).
- If timestamps are needed, they MUST use injected `Clock` (never `Instant.now()`).
- Message key MUST be stable and derived from domain identity (idempotency support).

---

## K3. Consumer Template (Binding)

### K3.1 Consumer Listener (delegates to service)

```java
@Component
@RequiredArgsConstructor
public class {Consumer} {

    private final {Resource}Service service;

    @KafkaListener(
        topics = "{Topic}",
        groupId = "{GroupId}"
    )
    public void onMessage({Event} {event}) {
        // 1) Validate minimal invariants (no business rules)
        // 2) Delegate to service in a single line
        service.handle({event});
    }
}
```

**Binding Rules:**
- Consumers MUST be `@Component` and constructor-injected.
- Consumer methods MUST contain no business logic.
- Consumer MUST delegate to service in a single line.
- Consumer group id MUST be explicit (no defaults).
- If retries/DLT are configured in the repo, follow repo conventions (do not invent).

---

## K4. Error Handling Patterns (Binding)

### K4.1 Idempotent Handler Pattern

```java
@Service
@RequiredArgsConstructor
@Transactional
public class {Resource}Service {

    private final {Resource}Repository repository;
    private final Clock clock;

    public void handle({Event} {event}) {
        // 1) Idempotency check (example)
        // if (repository.existsByExternalEventId({event}.getEventId())) return;

        // 2) Apply state change using entity methods
        // 3) Persist
        // 4) Record event id if the repo uses event-deduplication
    }
}
```

**Binding Rules:**
- Kafka handlers MUST be idempotent when the event model provides a stable event id.
- Persistence MUST be transactional when applying changes.
- Business logic placement MUST follow the decision tree in base templates (Section 16 of `rules.backend-java-templates.md`).

---

## K5. Kafka Test Templates (Binding)

### K5.1 Embedded Kafka Integration Test (spring-kafka-test)

```java
@SpringBootTest
@EmbeddedKafka(partitions = 1, topics = "{Topic}")
class {Consumer}IntegrationTest {

    @Autowired
    private KafkaTemplate<String, {Event}> kafkaTemplate;

    private static final Instant FIXED_TIME =
        Instant.parse("2026-01-31T10:00:00Z");

    @Test
    void publish_and_consume_should_process_event() {
        // GIVEN
        {Event} {event} = /* build a deterministic event */ null;

        // WHEN
        kafkaTemplate.send("{Topic}", String.valueOf({event}.get{Key}()), {event});

        // THEN
        // Use Awaitility to wait for async processing (do not sleep)
        // await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> { ... assertions ... });
    }
}
```

**Binding Rules:**
- Kafka integration tests MUST be deterministic (fixed time, stable keys).
- Tests MUST use Awaitility (or repo-standard async waiting) instead of `Thread.sleep`.
- Tests MUST assert externally observable outcomes (DB state, produced messages, etc.), not internal calls.

---

## K6. Integration Checklist (Binding)

- ✅ Producer uses KafkaTemplate with stable key
- ✅ Consumer delegates to service, no business logic in listener
- ✅ Clock used for timestamps everywhere
- ✅ Idempotency considered where event ids exist
- ✅ Tests deterministic and async-safe (Awaitility / repo standard)

---

**END OF KAFKA TEMPLATE ADDON**

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
