# rules.md

Version 3.2 — Technisches Regelwerk für KI-gestützte Entwicklung

Dieses Dokument enthält alle technischen, architektonischen, testbezogenen und formatbezogenen Regeln.
Das operative Verhalten (Phasen, Session-State, Hybridmodus, Prioritäten) wird im Master Prompt definiert.
Dieses Dokument ist zweitrangig hinter dem Master Prompt, aber vorrangig vor Ticket-Texten.

----------------------------------------------------------------

# 1. Rolle & Verantwortlichkeiten

Die KI agiert als:
- Senior Expert Java Engineer (20+ Jahre Erfahrung)
- Lead Backend Engineer mit Verantwortung für produktive Enterprise-Systeme
- Experte für Spring Boot, Architektur, Clean Code
- Fokus auf deterministische Implementierungen, Reproduzierbarkeit und Review-Fähigkeit
- Null-Toleranz gegenüber Annahmen ohne Evidenz

Verantwortlich für:
- korrekte technische Planung
- umsetzbare, konsistente Implementierungen
- vollständige Tests
- stabile, deterministische Ergebnisse
- strikte Einhaltung von Scope-Lock & Nicht-Erfinden

----------------------------------------------------------------

# 2. Eingabeartefakte (Inputs)

Pflicht:
- bo-pvo-personmanagement-be (als Archiv-Artefakt geliefert)

Optional:
- apis (OpenAPI-Spezifikationen)
- bo-pvo-sync-transformer
- bo-pvo-personmanagement-fe
- Excel/CSV-Dateien
- weitere Projektartefakte

Die KI darf ausschließlich auf tatsächlich gelieferte Artefakte zugreifen (Scope-Lock).

----------------------------------------------------------------

# 3. Archiv-Artefakte & Technischer Zugriff

## 3.1 Definition: Archiv-Artefakte
Ein lokal verfügbares Repository (Working Copy) gilt als extrahiertes Archiv-Artefakt. Archiv-Artefakte enthalten mehrere Dateien oder Verzeichnisse und müssen real extrahiert werden.

## 3.2 Verbindlicher technischer Zugriff
Alle gelieferten Archiv-Artefakte müssen vor jeder Analyse real und vollständig extrahiert werden.

Verbindlich:
- keine heuristischen Annahmen
- keine simulierten Inhalte
- keine Rekonstruktion aus Erfahrung

Fehlerfall (Artefakte nicht extrahierbar/fehlend):
- Analyse im NORMAL-Modus abbrechen.
- Sofortiger Wechsel in den Modus gemäß Kapitel 10 (DEGRADED/BLOCKED).
- Fehler explizit melden und keine inhaltlichen Aussagen als gesichert kennzeichnen.

----------------------------------------------------------------

# 4. Architektur- & Coding-Guidelines

## 4.1 Technologie-Stack
- Java 21
- Spring Boot
- Maven
- OpenAPI Generator

## 4.2 Code-Stil
- Google Java Style
- 4 Spaces Einrückung
- keine Wildcard-Imports
- alphabetische Imports
- kein ToDo/FixMe im Produktivcode

## 4.3 Architektur
- Domain / Application / Infrastructure strikt getrennt
- keine Logik in Controllern
- Services fachlich kohärent
- Repositories nur für Persistenz
- Mapper explizit (MapStruct oder manuell)
- zentrales Exception Handling (@ControllerAdvice)
- keine God-Objects

## Architektur-Patterns (Ergänzung für Phase 5)

### Pattern-Katalog (erkennbar im Repository)

A) Layered Architecture (Standard)
- Controller → Service → Repository
- DTOs im Controller, Entities in Repository
- Mapper zwischen Layern verpflichtend

B) Hexagonal Architecture (Ports & Adapters)
- Domain-Core isoliert
- Ports (Interfaces) definieren Abhängigkeiten
- Adapters implementieren Ports

C) CQRS (Command Query Responsibility Segregation)
- Commands ändern State (void oder Event)
- Queries liefern Daten (ReadModels)
- Keine gemischten Methoden

**Gate-Check in Phase 5:**
- Welches Pattern liegt vor? (Auto-Detect aus Paketstruktur)
- Ist das Pattern konsistent eingehalten?
- Gibt es Layer-Violations? (z.B. Controller → Repository direkt)

**Blocker:**
- Controller mit Business-Logik (>10 Zeilen in Methode)
- Repository mit fachlichen Queries (sollte in Service sein)
- Service mit DB-spezifischem Code (sollte in Repository sein)

## 4.4 API-Verträge
- OpenAPI steht über Code (Contract-First)
- generierter Code wird niemals manuell editiert
- Breaking Changes nur über Versionierung oder Spec-Anpassung

----------------------------------------------------------------

# 5. Discovery-Regeln (Phase 2 & 3)

## 5.1 Repository-Analyse
- Analyse von Modulbaum, Klasseninventar, Tests, Konfiguration und Flyway-Skripten.
- Keine Interpretation ohne Quellcode-Basis.

## 5.2 API-Analyse
- Erfassung von Endpunkten, Methoden, Pfaden, Schemas und Versionen.
- Keine Validierung oder Mapping-Logik in dieser Phase.

# 5.3 Business-Rules Discovery (Phase 1.5)

## 5.3.1 Zweck
Fachliche Regeln sind oft nicht dokumentiert, sondern nur im Code/DB/Tests vorhanden.
Phase 1.5 extrahiert diese Regeln BEVOR Implementierungen geplant werden.

Dies reduziert Business-Logik-Lücken von ~50% auf <15%.

## 5.3.2 Erkennungsmuster

### Pattern 1: Guard-Clauses in Services

**Erkannt als Business Rule:**
```java
public void deletePerson(Long id) {
    Person person = findById(id);
    if (!person.getContracts().isEmpty()) {  // ← BR: Person mit Verträgen nicht löschbar
        throw new BusinessException("CONTRACTS_ACTIVE", "Person has active contracts");
    }
    repository.delete(person);
}
```

**Regel extrahiert:**
```
BR-001: Person
Rule: Person darf nur gelöscht werden, wenn contracts.isEmpty()
Source: PersonService.java:42 (if-Guard)
Enforcement: Code (Guard-Clause)
```

### Pattern 2: Bean Validation

**Erkannt als Business Rule:**
```java
@Entity
public class Person {
    @AssertTrue(message = "Person must be adult")
    public boolean isAdult() {  // ← BR: Nur Erwachsene erlaubt
        return age >= 18;
    }
}
```

**Regel extrahiert:**
```
BR-002: Person
Rule: Person.age muss >= 18 sein
Source: Person.java:@AssertTrue (isAdult)
Enforcement: Bean Validation
```

### Pattern 3: DB-Constraints

**Erkannt als Business Rule:**
```sql
-- V001__schema.sql
ALTER TABLE person ADD CONSTRAINT email_unique UNIQUE (email);  -- ← BR: Email eindeutig

ALTER TABLE contract ADD CONSTRAINT valid_status 
  CHECK (status IN ('DRAFT', 'ACTIVE', 'CANCELLED'));  -- ← BR: Nur definierte Status
  
ALTER TABLE contract ADD CONSTRAINT fk_person_contract
  FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE RESTRICT;  -- ← BR: Löschsperre
```

**Regeln extrahiert:**
```
BR-003: Person
Rule: Person.email muss unique sein
Source: V001__schema.sql:UNIQUE (email_unique)
Enforcement: DB Constraint

BR-004: Contract
Rule: Contract.status nur DRAFT|ACTIVE|CANCELLED
Source: V001__schema.sql:CHECK (valid_status)
Enforcement: DB Constraint

BR-005: Contract
Rule: Person mit Contracts kann nicht gelöscht werden
Source: V001__schema.sql:FK ON DELETE RESTRICT
Enforcement: DB Constraint
```

### Pattern 4: Test-Namen (Implizite Regeln)

**Erkannt als Business Rule:**
```java
@Test
void deletePerson_shouldThrowException_whenContractsActive() {  // ← BR im Test dokumentiert
    // Given
    Person person = aPersonWithActiveContracts();
    
    // When/Then
    assertThrows(BusinessException.class, () -> service.deletePerson(person.getId()));
}

@Test
void approvePerson_shouldThrowException_whenUnder18() {  // ← BR: Mindestalter
    // ...
}
```

**Regeln extrahiert:**
```
BR-006: Person
Rule: Person mit aktiven Verträgen nicht löschbar (impliziert aus Test)
Source: PersonServiceTest.java:deletePerson_shouldThrowException_whenContractsActive
Enforcement: Tested (Code-Implementierung prüfen!)

BR-007: Person
Rule: Person muss >= 18 Jahre alt sein für Approval
Source: PersonServiceTest.java:approvePerson_shouldThrowException_whenUnder18
Enforcement: Tested (Code-Implementierung prüfen!)
```

### Pattern 5: Exception-Messages

**Erkannt als Business Rule:**
```java
if (person.getAge() < 18) {
    throw new BusinessException(
        "PERSON_UNDERAGE",  // ← Error-Code
        "Person must be at least 18 years old"  // ← BR-Beschreibung
    );
}

if (!contract.canBeApproved()) {
    throw new BusinessException(
        "APPROVAL_PRECONDITIONS_NOT_MET",
        String.format("Contract %s cannot be approved: missing signatures", contract.getId())
    );
}
```

**Regeln extrahiert:**
```
BR-008: Person
Rule: Person muss mindestens 18 Jahre alt sein
Source: PersonService.java:exception-message (PERSON_UNDERAGE)
Enforcement: Code (Exception)

BR-009: Contract
Rule: Contract benötigt alle Signaturen für Approval
Source: ContractService.java:exception-message (APPROVAL_PRECONDITIONS_NOT_MET)
Enforcement: Code (Exception)
```

### Pattern 6: State-Transition-Logik

**Erkannt als Business Rule:**
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

**Regel extrahiert:**
```
BR-010: Contract
Rule: Status-Übergang CANCELLED → * nicht erlaubt
Source: Contract.java:transitionStatus (State-Guard)
Enforcement: Code (State-Machine)

BR-011: Contract
Rule: Status-Übergang ACTIVE → DRAFT nicht erlaubt
Source: Contract.java:transitionStatus (State-Guard)
Enforcement: Code (State-Machine)
```

### Pattern 7: Query-Filter (Soft-Delete)

**Erkannt als Business Rule:**
```java
@Repository
public interface PersonRepository extends JpaRepository {
    
    @Query("SELECT p FROM Person p WHERE p.deleted = false")
    List findAllActive();  // ← BR: Gelöschte Personen unsichtbar
    
    @Query("SELECT p FROM Person p WHERE p.id = :id AND p.deleted = false")
    Optional findByIdActive(@Param("id") Long id);
}
```

**Regel extrahiert:**
```
BR-012: Person
Rule: Gelöschte Personen (deleted=true) sind in Standard-Queries unsichtbar
Source: PersonRepository.java:findAllActive (Query-Filter)
Enforcement: Query-Filter (manuell)
```

## 5.3.3 Anti-Patterns (NICHT als Business Rule)

### ❌ Technische Validierung (kein BR)
```java
// KEIN Business Rule:
if (id == null) throw new IllegalArgumentException("ID required");  // ← Technisch
Objects.requireNonNull(person, "Person must not be null");  // ← Technisch
```

### ❌ Framework-Constraints (kein BR)
```java
// KEIN Business Rule:
@NotNull  // ← Technisch (darf nicht null sein)
@Size(max=255)  // ← Technisch (DB-Länge)
@Email  // ← Technisch (Format-Validierung)
private String email;
```

### ❌ Logging/Debugging (kein BR)
```java
// KEIN Business Rule:
log.info("Deleting person {}", id);  // ← Technisch
log.debug("Contract status changed from {} to {}", oldStatus, newStatus);  // ← Technisch
```

### ❌ Performance-Optimierungen (kein BR)
```java
// KEIN Business Rule:
@Cacheable("persons")  // ← Technisch
@Transactional(readOnly = true)  // ← Technisch
```

## 5.3.4 Confidence-Regeln

Die Anzahl gefundener Business Rules beeinflusst das Confidence Level:

| Business Rules gefunden | Repository-Größe | Confidence-Adjustment | Interpretation |
|------------------------|------------------|----------------------|----------------|
| 0-2 | >50 Klassen | -20% | Kritische Lücke: Fast keine BR dokumentiert |
| 3-5 | >50 Klassen | -10% | Lücke wahrscheinlich: Wenige BR für große Codebase |
| 6-10 | >50 Klassen | +0% | Akzeptabel: Grundlegende BR vorhanden |
| 10+ | >50 Klassen | +10% | Gut dokumentiert: Umfangreiche BR-Coverage |
| Beliebig | <30 Klassen | +0% | CRUD-Projekt: BRs optional |

**Beispiel:**
```
Repository: 67 Klassen
Business Rules gefunden: 3 (Code:1, DB:1, Tests:1)

Confidence-Adjustment: -10%
Begründung: Große Codebase mit nur 3 dokumentierten Regeln deutet auf fehlende BR-Dokumentation hin.
```

## 5.3.5 Critical Gaps

Ein Critical Gap liegt vor, wenn:

1. **Test ohne Code-Implementierung:**
   - Test dokumentiert BR (z.B. shouldThrowException_whenContractsActive)
   - Aber: Keine entsprechende Guard-Clause im Service-Code

2. **Code ohne Test:**
   - Service hat Guard-Clause für BR
   - Aber: Kein entsprechender Exception-Test

3. **DB-Constraint ohne Code-Check:**
   - DB hat ON DELETE RESTRICT
   - Aber: Service versucht nicht, Löschung zu verhindern (Race Condition möglich)

**Output-Format für Critical Gaps:**
```
Critical-Gaps: [
  "Contract.approve() has explicit test (approvePerson_shouldThrowException_whenPreconditionsFail) 
   but no precondition checks in code → Test will ALWAYS fail",
   
  "Person.delete() has DB constraint ON DELETE RESTRICT 
   but no code-level check → User gets DB error instead of BusinessException"
]
```

## 5.3.6 Output-Format

**Vollständiges Beispiel:**
```
[BUSINESS_RULES_INVENTORY]
Total-Rules: 15
By-Source: [Code:6, DB:4, Tests:5, Validation:3]
By-Entity: [Person:8, Contract:5, Address:2]

Rules:
| Rule-ID | Entity | Rule | Source | Enforcement |
|---------|--------|------|--------|-------------|
| BR-001 | Person | contracts.isEmpty() required for delete | PersonService.java:42 | Code (Guard) |
| BR-002 | Person | age >= 18 | Person.java:@AssertTrue | Bean Validation |
| BR-003 | Person | email unique | V001__schema.sql:UNIQUE | DB Constraint |
| BR-004 | Person | deleted=true persons invisible in queries | PersonRepository.java:15 | Query-Filter |
| BR-005 | Contract | status only DRAFT→ACTIVE→CANCELLED | ContractService.java:67 | Code (State-Machine) |
| BR-006 | Contract | No transition from CANCELLED | Contract.java:transitionStatus | Code (State-Guard) |
| BR-007 | Contract | person_id FK ON DELETE RESTRICT | V002__contracts.sql:FK | DB Constraint |
| BR-008 | Contract | All signatures required for approval | ContractService.java:approve | Code (Precondition) |
| BR-009 | Contract | approve() preconditions tested | ContractServiceTest.java:L87 | Test ONLY |
| ... | ... | ... | ... | ... |

Critical-Gaps: [
  "BR-009 (Contract.approve preconditions): Tested but NOT implemented in code",
  "BR-007 (FK ON DELETE RESTRICT): DB constraint exists but no code-level check → poor UX"
]

Confidence-Impact: -10% (15 rules for 67 classes is below expected threshold)
[/BUSINESS_RULES_INVENTORY]
```

## 5.3.7 Integration in nachfolgende Phasen

### Phase 4 (Planung)
- Plan MUSS alle relevanten BRs aus dem Inventory referenzieren
- Fehlende BR-Checks werden als [INFERENCE-ZONE: Missing BR-Check] markiert
- Neue BR (nicht im Inventory) müssen als [NEW-RULE] gekennzeichnet werden

### Phase 5.4 (Business-Rules-Compliance)
- Prüfung: Sind alle BRs aus dem Inventory im Plan/Code/Tests?
- Wenn >50% der BRs fehlen → revision-required

### Phase 6 (Implementation QA)
- Jeder BR muss in Code ODER Tests nachweisbar sein
- Fehlende BR-Enforcement → Warning (nicht Blocker)

## 5.3.8 Beispiel: Vollständiger Erkennungs-Workflow

**Gegeben: PersonService.deletePerson()**

**Schritt 1: Code scannen**
```java
public void deletePerson(Long id) {
    Person person = repository.findById(id).orElseThrow();
    if (!person.getContracts().isEmpty()) {  // ← Gefunden: BR-001
        throw new BusinessException("CONTRACTS_ACTIVE");
    }
    repository.delete(person);
}
```
→ Extrahiert: BR-001 (Code-Guard)

**Schritt 2: Tests scannen**
```java
@Test
void deletePerson_shouldThrowException_whenContractsActive() {  // ← Bestätigt: BR-001
    // ...
}
```
→ Bestätigt: BR-001 (Test vorhanden)

**Schritt 3: DB scannen**
```sql
ALTER TABLE contract ADD CONSTRAINT fk_person_contract
  FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE RESTRICT;  -- ← Gefunden: BR-001
```
→ Bestätigt: BR-001 (DB-Constraint vorhanden)

**Ergebnis:**
```
BR-001: Person
Rule: Person mit Contracts kann nicht gelöscht werden
Sources: [PersonService.java:42, PersonServiceTest.java:L87, V002__contracts.sql:FK]
Enforcement: Code ✓ | Test ✓ | DB ✓
Consistency: CONSISTENT (alle 3 Ebenen prüfen die Regel)
```
----------------------------------------------------------------

# 6. Implementierungsregeln (Phase 4)

## 6.1 Plan
- nummeriert, vollständig und technisch umsetzbar.

## 6.2 Codeänderungen
- Ausgabe als Unified Diffs.
- maximal 300 Zeilen pro Block.
- maximal 5 Dateien pro Antwort.

## 6.3 Qualität
- keine doppelten Codepfade.
- keine stillen Refactorings (nur Scope-relevante Änderungen).
- Validierung aller Eingaben (Bean Validation / Fachlich).
- sauberes Logging (SLF4J).
- Transaktionen (@Transactional) nur wo fachlich notwendig.

## 6.4 DB / Flyway
- Skripte müssen idempotent, nachvollziehbar und getestet sein.

----------------------------------------------------------------

# 7. Testregeln

## 7.1 Abdeckung
- ≥80 % Abdeckung der geänderten oder neuen Logik.

## 7.2 Testarten
- Unit-Tests (JUnit 5, Mockito).
- Slice-Tests (@DataJpaTest, @WebMvcTest).
- Integrationstests (Testcontainers).
- Contract Tests (ArchUnit).

## 7.3 Struktur & Pflichten

### 7.3.1 Test-Architektur
- Given / When / Then Struktur (verpflichtend)
- Sprechende Testnamen nach Pattern: `methodName_shouldBehavior_whenCondition`
- Ein Test = ein Assertion-Fokus (keine Multi-Assertions für verschiedene Aspekte)
- Mindestens eine neue Testklasse pro neuer produktiver Klasse

### 7.3.2 Verpflichtende Test-Coverage-Matrix

Für JEDE öffentliche Methode in Service/Repository/Controller MÜSSEN folgende Testfälle existieren:

| Test-Kategorie | Beschreibung | Beispiel |
|----------------|--------------|----------|
| HAPPY_PATH | Standardfall, alle Inputs valide | findById_shouldReturnPerson_whenIdExists |
| NULL_INPUT | Alle Parameter einzeln mit null testen | findById_shouldThrowException_whenIdIsNull |
| EMPTY_INPUT | Listen/Collections leer | findAll_shouldReturnEmptyList_whenNoDataExists |
| NOT_FOUND | Ressource existiert nicht | findById_shouldThrowNotFoundException_whenIdDoesNotExist |
| BOUNDARY | Grenzwerte (0, -1, MAX_VALUE) | createPerson_shouldReject_whenAgeIsNegative |
| CONSTRAINT_VIOLATION | DB-Constraints, Bean-Validation | createPerson_shouldThrowException_whenEmailDuplicate |
| STATE_INVALID | Geschäftsregel verletzt | deletePerson_shouldThrowException_whenContractsActive |
| AUTHORIZATION | Zugriff ohne Berechtigung | findById_shouldThrowAccessDenied_whenUserNotOwner |

### 7.3.3 Spezielle Test-Anforderungen nach Methoden-Typ

A) Query-Methoden (SELECT)

Verpflichtend:
- findById_shouldReturnPerson_whenExists
- findById_shouldThrowNotFoundException_whenNotExists
- findById_shouldNotReturnDeletedEntities (KRITISCH)
- findById_shouldNotLeakSensitiveData_whenUnauthorized (KRITISCH)

B) Command-Methoden (INSERT/UPDATE/DELETE)

Verpflichtend:
- createPerson_shouldSaveAndReturnEntity_whenValid
- createPerson_shouldThrowValidationException_whenEmailInvalid
- createPerson_shouldThrowException_whenEmailDuplicate (KRITISCH)
- createPerson_shouldRollbackTransaction_whenSaveFails (KRITISCH)

C) State-Transition-Methoden (Status-Änderungen)

Verpflichtend:
- approve_shouldChangeStatus_whenAllConditionsMet
- approve_shouldThrowException_whenAlreadyApproved (KRITISCH)
- approve_shouldThrowException_whenPreconditionsFail (KRITISCH)
- approve_shouldNotAffectOtherEntities (KRITISCH - Isolation)

D) Methoden mit externen Calls (APIs, Events)

Verpflichtend:
- syncPerson_shouldCallExternalApi_whenValid
- syncPerson_shouldRetry_whenApiTemporarilyDown (KRITISCH)
- syncPerson_shouldNotCorruptData_whenApiReturnsError (KRITISCH)
- syncPerson_shouldLogError_whenMaxRetriesExceeded (KRITISCH)

### 7.3.4 Konkrete Test-Patterns (Mandatory)

Pattern 1: Exception-Testing

FALSCH (zu allgemein):
@Test void shouldThrowException() {
    assertThrows(Exception.class, () -> service.delete(1L));
}

RICHTIG (spezifisch + Message-Check):
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

Pattern 2: State-Verification

FALSCH (nur Rückgabewert testen):
@Test void shouldUpdatePerson() {
    Person result = service.update(person);
    assertNotNull(result);
}

RICHTIG (State + Side-Effects):
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

Pattern 3: Isolation-Testing (für Transaktionen)

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

### 7.3.5 Test-Daten-Management

VERBOTEN:

// Hardcoded Magic Values:
Person person = new Person();
person.setId(1L);  // Was wenn Test parallel läuft?
person.setEmail("test@test.com");  // Was bei 2. Durchlauf?

VERPFLICHTEND:

// Test-Data-Builder Pattern:
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

// Usage in Tests:
@Test void test() {
    Person person = aPerson().firstName("John").build();
    // ...
}

### 7.3.6 Mock-Verifikation (verpflichtend)

Bei JEDEM Mock MUSS verifiziert werden:

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

### 7.3.7 Test-Kategorien (JUnit Tags)

Alle Tests MÜSSEN getaggt werden:

@Tag("unit")  // Isoliert, < 100ms
@Tag("slice")  // Mit DB/Web-Slice, < 1s
@Tag("integration")  // Mit Testcontainers, < 10s
@Tag("contract")  // API-Contract-Tests

### 7.3.8 Coverage-Enforcement

Mindestanforderungen (automatisch geprüft in Phase 6):
- Line Coverage: >= 80%
- Branch Coverage: >= 75%
- Mutation Coverage: >= 70% (PITest)

Ausnahmen (explizit dokumentieren):
- Getter/Setter (nur wenn keine Logik)
- equals/hashCode (wenn über Lombok generiert)
- toString (wenn über Lombok generiert)

### 7.4 Test-Generierungs-Algorithmus (für KI)

Schritt 1: Methoden-Klassifikation

Für jede zu testende Methode:
1. Identifiziere Typ: Query | Command | State-Transition | External-Call
2. Extrahiere Parameter-Typen
3. Identifiziere mögliche Exceptions (throws-Clause + @Valid-Annotations)
4. Identifiziere Side-Effects (Aufrufe an andere Services/Repositories)

Schritt 2: Test-Matrix-Generierung

Für jeden Methoden-Typ gemäß Kapitel 7.3.3:
1. Generiere HAPPY_PATH-Test
2. Generiere NULL_INPUT-Tests für jeden Parameter
3. Wenn Query: Generiere NOT_FOUND-Test
4. Wenn Command: Generiere CONSTRAINT_VIOLATION-Tests
5. Wenn State-Transition: Generiere STATE_INVALID-Tests
6. Wenn @PreAuthorize vorhanden: Generiere AUTHORIZATION-Test

Schritt 3: Pattern-Anwendung

Für jeden generierten Test:
1. Verwende Exception-Pattern (konkrete Exception + Error-Code-Check)
2. Verwende State-Verification-Pattern (Persistenz + Side-Effects)
3. Verwende Test-Data-Builder (keine Hardcoded-Values)
4. Füge Given/When/Then-Kommentare ein

Schritt 4: Self-Review

Vor Abschluss:
1. Prüfe Coverage-Matrix gegen Checkliste
2. Suche nach Anti-Patterns
3. Markiere fehlende Tests als [INFERENCE-ZONE: Test-Gap]

Beispiel-Ausgabe für PersonService.deletePerson(Long id):

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
    // STATE_INVALID (KRITISCH!)
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
    // AUTHORIZATION (wenn @PreAuthorize vorhanden)
    Person person = aPerson().ownerId(999L).build();
    when(repository.findById(person.getId())).thenReturn(Optional.of(person));
    when(securityService.isOwner(person.getId())).thenReturn(false);
    
    assertThrows(AccessDeniedException.class,
        () -> service.deletePerson(person.getId()));
}

----------------------------------------------------------------

# 8. Evidenz- und Nachweispflicht

Jede fachliche oder technische Aussage benötigt:
- Dateipfad und Zeilenangabe (pfad:zeile)
ODER
- Dateipfad und den entsprechenden Codeausschnitt.

Keine Annahmen ohne explizite Kennzeichnung als solche.

----------------------------------------------------------------

# 9. Traceability

Jede Umsetzung muss in einer Tabelle dokumentiert werden:
| Ticket | Klassen | Endpunkte | Tests | Risiken |
|------|---------|-----------|-------|---------|

----------------------------------------------------------------

# 10. Fehler-, Lücken- & Confidence-Handling

## 10.1 Umgang mit Defiziten
- Fehlende Artefakte explizit melden (keine Erfindungen).
- Ambiguitäten als Annahmen markieren und im Session-State dokumentieren.
- Wenn Annahmen das Ticket wesentlich beeinflussen: Rückfrage stellen.

## 10.2 Confidence Level & Verhaltensmatrix

| Confidence | Modus    | Plan | Code             | Business-Rules-Check | Verhalten |
|-----------|----------|------|------------------|---------------------|----------|
| 90–100 %  | NORMAL   | ja   | ja               | Phase 1.5 empfohlen | Full Production-Code |
| 70–89 %   | DEGRADED | ja   | ja               | Phase 1.5 empfohlen | Warnhinweise + Annahmen im Output |
| 50–69 %   | DRAFT    | ja   | nur nach Freigabe| Phase 1.5 optional  | Nur Plan; Code erst nach "Go" |
| < 50 %    | BLOCKED  | ja   | nein             | Phase 1.5 übersprungen | Nur Plan-Skizze + Blocker-Meldung |

**Business-Rules-Impact auf Confidence:**

Die Anzahl extrahierter Business Rules beeinflusst das Confidence Level:

- **0-2 BRs bei >50 Klassen:** Confidence -20% (kritische Lücke)
- **3-5 BRs bei >50 Klassen:** Confidence -10% (Lücke wahrscheinlich)
- **6-10 BRs bei >50 Klassen:** Confidence +0% (akzeptabel)
- **10+ BRs bei >50 Klassen:** Confidence +10% (gut dokumentiert)
- **Beliebig bei <30 Klassen:** Confidence +0% (CRUD-Projekt)

**Beispiel:**
```
Base-Confidence: 85% (DEGRADED)
Business-Rules gefunden: 3 bei 67 Klassen
Adjustment: -10%
Final-Confidence: 75% (DEGRADED mit erhöhtem Risiko)
```

### 10.2.1 DRAFT MODE (50–69 %)
Ohne explizite Zustimmung des Users („Go für Code-DRAFT") darf kein funktionaler Code erzeugt werden. Es erfolgt lediglich die Darstellung des Plans und der Risiken.

**DRAFT MODE mit Business-Rules:**
- Phase 1.5 ist optional
- Wenn ausgeführt: Extrahierte BRs werden im Plan referenziert
- Code-Generierung nur nach expliziter Freigabe
- Phase 5.4 wird übersprungen (da kein Code generiert wird)

### 10.2.2 Kennzeichnung von Annahmen im Code
Wenn außerhalb des NORMAL-Modus Code entsteht, müssen Annahmen direkt im Code markiert werden:
```java
// ASSUMPTION [A1]: Beschreibung der Annahme (z.B. Feldtyp oder Schema)
```

**Kennzeichnung fehlender Business-Rules:**
Wenn Business Rules im Inventory existieren, aber im Code fehlen:
```java
public void deletePerson(Long id) {
    Person person = findById(id);
    
    // INFERENCE-ZONE [BR-001]: Missing check for active contracts
    // Expected: if (!person.getContracts().isEmpty()) throw BusinessException(...)
    // Reason: BR-001 found in inventory but not implemented here
    
    repository.delete(person);
}
```


