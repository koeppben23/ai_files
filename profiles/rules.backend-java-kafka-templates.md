# Backend Java - Kafka Code & Test Templates (ADDON)

**Purpose (binding):** Provide concrete copy-paste templates so the assistant generates deterministic, reviewable Kafka producers/consumers and tests in backend-java repos.

**Addon class (binding):** required addon.

**Activation (binding):** MUST be loaded at code-phase (Phase 4+) when Kafka is required (see `rules.backend-java.md`).
- If Kafka is required and this addon is not loaded: `Mode = BLOCKED`, `Next = BLOCKED-MISSING-ADDON:kafka`.

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

