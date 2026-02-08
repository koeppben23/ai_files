# Backend Java - Kafka Code & Test Templates (ADDON)

## Intent (binding)

Provide concrete copy-paste templates so the assistant generates deterministic, reviewable Kafka producers/consumers and tests in backend-java repos.

## Scope (binding)

Kafka producer/consumer code paths, idempotency/retry behavior, and Kafka-related test evidence for backend-java repositories.

## Activation (binding)

Addon class: `required`.

This addon MUST be loaded at code-phase (Phase 4+) when Kafka is required (see `rules.backend-java.md`).
- Missing-addon handling MUST follow canonical required-addon policy from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`.
- This rulebook MUST NOT redefine blocking semantics.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This required addon refines Kafka-specific templates and MUST NOT override `master.md`, `rules.md`, `rules.backend-java.md`, or base template constraints.

## Phase integration (binding)

- Phase 2: capture Kafka evidence (deps/annotations/config) and required scope.
- Phase 4: apply these templates only for Kafka-touched changes.
- Phase 5.3: verify idempotency/retry/error-path behavior with deterministic evidence.

## Evidence contract (binding)

When active, maintain:
- `SESSION_STATE.AddonsEvidence.kafka.required`
- `SESSION_STATE.AddonsEvidence.kafka.signals`
- `SESSION_STATE.AddonsEvidence.kafka.status` (`loaded|skipped|missing-rulebook`)
- tier/gate evidence refs for idempotency, retry/DLT behavior, and async test stability.

## Tooling (binding)

- Use repository-pinned Kafka/Spring tooling when present; do not invent alternate client stacks.
- Preserve repo serializer/deserializer strategy unless ticket explicitly changes it.
- Test tooling should follow repo standard (`spring-kafka-test`, Testcontainers, or existing equivalent).

## Correctness by construction (binding)

Inputs required:
- topic name and event schema contract
- consumer group / key strategy
- target module/package path

Outputs guaranteed:
- producer/consumer scaffolds with deterministic keying and explicit delegation
- async test scaffold with deterministic waits (no sleep-based control)
- retry/DLT hooks aligned to repo conventions when present

Evidence expectation:
- after template application, run repo-native Kafka/unit/integration tests (or mark `not-verified` with recovery command)
- idempotency/retry claims MUST reference BuildEvidence item ids.

Golden examples:
- listener validates minimally and delegates to service in one line.
- Kafka test uses stable keys + Awaitility/Testcontainers evidence.

Anti-example:
- listener embeds business branching with side effects and no replay/idempotency proof.

## Examples (GOOD/BAD)

GOOD:
- Listener performs minimal validation and delegates in one line to service; idempotency check is proven by test evidence.

BAD:
- Listener contains business branching with side effects and no replay/idempotency proof.

GOOD:
- Kafka test uses stable keys, deterministic event data, and Awaitility-based async assertions.

BAD:
- Kafka test uses `Thread.sleep` and random keys while asserting internal implementation calls.

## Troubleshooting

- Schema registry mismatch: align serializer config and test fixtures with repo convention before changing listeners.
- Retry/DLT ambiguity: prefer existing retry topology; if unknown, mark `not-verified` and emit recovery command.
- Async flake in tests: replace sleeps with Awaitility/Testcontainers-ready checks.

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

---
## Java-first Principal Hardening v2 - Kafka Critical Gate (Binding)

### KPH2-1 Kafka scorecard criteria (binding)

When Kafka scope is touched, the scorecard MUST include and evaluate:

- `KAFKA-DETERMINISTIC-TIME-SEAMS`
- `KAFKA-STABLE-KEY-AND-PARTITIONING`
- `KAFKA-IDEMPOTENCY-PROVEN`
- `KAFKA-RETRY-DLT-BEHAVIOR-VERIFIED` (if repo uses retries/DLT)
- `KAFKA-ASYNC-TEST-STABILITY`

Each criterion MUST carry an `evidenceRef`.

### KPH2-2 Required kafka test matrix (binding)

Kafka-related changes MUST include evidence for at least:

- publish/consume happy path
- duplicate event or replay path proving idempotency behavior
- one failure-path assertion (deserialization/validation/downstream failure) aligned with repo behavior

If a row is not applicable, explicit rationale is required.

### KPH2-3 Kafka hard fail conditions (binding)

Gate result MUST be `fail` if any applies:

- missing stable message key for event identity
- missing idempotency proof where stable event ids exist
- `Thread.sleep` used in changed async tests when Awaitility or equivalent exists
- listener contains business branching beyond minimal validation/delegation

### KPH2-4 Kafka warning codes (binding)

Use the following status codes with recovery steps when non-blocking handling is required:

- `WARN-KAFKA-IDEMPOTENCY-UNVERIFIED`
- `WARN-KAFKA-RETRY-POLICY-UNKNOWN`
- `WARN-KAFKA-ASYNC-FLAKINESS-RISK`

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
