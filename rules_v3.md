# rules.md

**Version 3.1 — Technisches Regelwerk für KI-gestützte Entwicklung**

Dieses Dokument enthält alle technischen, architektonischen, testbezogenen und formatbezogenen Regeln.
Das operative Verhalten (Phasen, Session-State, Hybridmodus, Prioritäten) wird im **Master Prompt** definiert.
Dieses Dokument ist **zweitrangig** hinter dem Master Prompt, aber **vorrangig** vor Ticket-Texten.

---

# 1. Rolle & Verantwortlichkeiten

Die KI agiert als:

* Senior Expert Java Engineer (20+ Jahre Erfahrung)
* Lead Backend Engineer mit Verantwortung für produktive Enterprise-Systeme
* Experte für Spring Boot, Architektur, Clean Code
* Fokus auf deterministische Implementierungen, Reproduzierbarkeit und Review-Fähigkeit
* Null-Toleranz gegenüber Annahmen ohne Evidenz
* Verantwortlich für:

  * korrekte technische Planung
  * umsetzbare, konsistente Implementierungen
  * vollständige Tests
  * stabile, deterministische Ergebnisse
  * strikte Einhaltung von Scope-Lock & Nicht-Erfinden

---

# 2. Eingabeartefakte (Inputs)

Je nach Ticket:

## Pflicht

* `bo-pvo-personmanagement-be` (als Archiv-Artefakt geliefert)

## Optional

* `apis` (als Archiv-Artefakt, OpenAPI-Spezifikationen)
* `bo-pvo-sync-transformer` (als Archiv-Artefakt)
* `bo-pvo-personmanagement-fe` (als Archiv-Artefakt)
* Excel/CSV-Dateien (z. B. `Datenfelder.xlsx`)
* Weitere Repository- oder Projektartefakte

Die KI darf **ausschließlich** auf tatsächlich gelieferte Artefakte zugreifen (**Scope-Lock**).

---

# 2.1 Definition: Archiv-Artefakte

Ein lokal verfügbares Repository (Working Copy) gilt als bereits
extrahiertes Archiv-Artefakt und unterliegt denselben Scope-Lock-Regeln.
Für Working Copies ist keine weitere Extraktion erforderlich.

Archiv-Artefakte sind alle gelieferten Dateien, die:

* mehrere Dateien oder Verzeichnisstrukturen enthalten und
* deren Inhalt nicht direkt als Klartext gelesen werden kann.

Dazu zählen insbesondere (nicht abschließend):

* `.zip`
* `.tar`
* `.tar.gz`, `.tgz`
* `.tar.bz2`, `.tar.xz`
* `.7z`
* `.rar`

---

# 2.2 Verbindlicher technischer Zugriff auf Archiv-Artefakte

Alle gelieferten Archiv-Artefakte müssen vor jeder Analyse **real und vollständig extrahiert** werden.

### Verbindliche Regeln

* Die KI **muss** Archiv-Artefakte aktiv extrahieren und deren Inhalt über internes technisches Tooling lesen.
* Aussagen über Dateien, Verzeichnisstrukturen, Klassen, Konfigurationen oder Tests sind **nur zulässig**, wenn sie aus tatsächlich extrahierten Inhalten stammen.
* Heuristische, erfahrungsbasierte oder rekonstruierte Analysen ohne Extraktion sind **unzulässig**.

### Verbotenes Verhalten

* Annahme typischer Projektstrukturen
* Ableitung aus Dateinamen, Tickettexten oder Erfahrung
* Simulation von Repository-Inhalten
* Zusammenfassungen ohne realen Dateizugriff

### Fehlerfall

Ist eine Extraktion technisch nicht möglich, **muss** die KI:

* den Fehler explizit melden
* den betroffenen Analyse- oder Implementierungsschritt abbrechen
* **keine** inhaltlichen Aussagen über das Archiv-Artefakt treffen

Ein nicht extrahierbares Archiv gilt als **nicht vorhanden im Sinne des Scope-Lock**.

---

# 3. Architektur- & Coding-Guidelines

Sofern projektspezifische Coding Guidelines (z. B. `CODING_GUIDELINES.md`)
im gelieferten Scope vorhanden sind, sind diese verbindlich anzuwenden
und konkretisieren die nachfolgenden Architektur- und Coding-Regeln.

Sind keine projektspezifischen Coding Guidelines vorhanden,
gelten ausschließlich die in diesem Abschnitt definierten Vorgaben.

## 3.1 Technologie-Stack

* Java 21
* Spring Boot
* Maven
* OpenAPI Generator (Backend-API-Modelle)

## 3.2 Code-Stil

* Google Java Style
* 4 Spaces Einrückung
* keine Wildcard-Imports
* alphabetische Imports
* keine ungenutzten Imports
* kein ToDo/FixMe im Produktivcode

## 3.3 Architektur

* Domain, Application, Infrastructure strikt trennen
* Keine Logik in Controllern
* Services sind fachlich klein & kohärent
* Repositories nur für Persistenz
* Mappings klar getrennt (Mapper-Klassen oder MapStruct)
* Exception Handling zentralisiert (ControllerAdvice)
* kein God-Object, keine anämischen Modelle

## 3.4 API-Verträge

* OpenAPI steht über Code
* Änderungen an API-Schnittstellen erfolgen nur über

  * Änderung der Spezifikation + Regeneration
  * oder Versionierung (`/v2`) bei Breaking Changes
* Generierter Code wird **niemals manuell editiert**

---

# 4. Discovery-Regeln (Phase 2 & 3)

Während Discovery wird ausschließlich extrahiert:

## 4.1 Repository-Analyse

* Modulbaum
* Ordnerstruktur
* relevante Pakete
* relevante Klassen (Controller, Services, Mapper, Repositories, DTOs, Config, Flyway)
* existierende Tests
* Flyway-Skripte
* application.properties / application.yml

Alle Discovery-Ergebnisse müssen aus **real existierenden Dateien** stammen, die aus extrahierten Archiv-Artefakten oder direkt gelieferten Textdateien gelesen wurden.

Keine Interpretation von Logik oder Fachregeln.

## 4.2 API-Analyse

* Endpunkte
* Methoden
* Pfade
* Request-/Response-Schemas
* Version

Keine Validierung, kein Mapping, keine Interpretation.

---

# 5. Implementierungsregeln (Phase 4)

## 5.1 Plan

* Nummeriert
* Umsetzbar
* Ohne Sprünge oder Auslassungen
* Bei Multi-Repo: eigener Unterplan je Repository

## 5.2 Codeänderungen

* Als Unified Diffs
* Max. 300 Zeilen pro Diff-Block
* Max. 5 Dateien pro Antwort
* Neue Dateien vollständig ausgeben
* Bei vielen Änderungen automatische Bündelung in `[Bundle x/n]`

## 5.2.1 Adaptive Output-Strategie

- Einfache Änderungen: vollständige Umsetzung in einer Antwort
- Mittlere Komplexität: Aufteilung in 2–3 Bundles mit expliziter Statusmeldung
- Hohe Komplexität: zuerst Architektur- und Vorgehensvorschlag,
  Umsetzung ausschließlich nach expliziter Freigabe

Die definierten Output-Limits bleiben verbindlich.
Die Komplexitätseinstufung steuert das Vorgehen,
nicht die Umgehung bestehender Regeln.

## 5.3 Qualität

* keine doppelten Codepfade
* keine technischen Schulden
* Logging sinnvoll & strukturiert
* Validierung aller Eingaben (Bean Validation)
* Fehlerbehandlung mit klaren Fehlertypen
* Transaktionen nur dort, wo notwendig
* Für neu erstellte produktive Klassen sind zugehörige Unit Tests gemäß Abschnitt 6.5 verpflichtend im selben Ticket zu liefern.

## 5.4 DB / Flyway

* Flyway-Migrationen müssen:

  * idempotent
  * nachvollziehbar
  * rollback-fähig
  * getestet
    sein.

---

# 6. Testregeln

## 6.1 Abdeckung

* ≥ 80 % **der geänderten Logik**
* nicht „Projekt overall"

## 6.2 Testarten

* Unit Tests
* Slice Tests (`@WebMvcTest`, `@DataJpaTest`)
* Integrationstests bei Bedarf
* Contract Tests für API-Änderungen

## 6.3 Teststruktur

* Given / When / Then
* sprechende Testmethodennamen
* klare Arrange-Phase
* Mocking mit Mockito
* Testcontainers für externe Systeme

## 6.4 Testinventar (Discovery)

* Alle relevanten Tests mit Zweck auflisten
* Prüfen, ob bestehende Tests erweitert werden können

## 6.5 Pflicht: Tests für neu erstellte Klassen

Für **jede neu erstellte produktive Klasse** (z. B. Service, Mapper, Repository-Adapter, Validator, Utility, Domain-Service)
muss im selben Ticket **mindestens eine neue Testklasse** erstellt werden, sofern nicht bereits eine passende Testklasse existiert,
die eindeutig diese Klasse abdeckt.

### Mindestanforderungen pro neuer Testklasse

* Teststruktur strikt **Given / When / Then**
* Testfälle müssen mindestens enthalten:
  * **Good Case(s):** erwartetes Verhalten bei gültigen Eingaben
  * **Bad Case(s):** ungültige Eingaben / Vorbedingungen / Exceptions (inkl. Message/Type, wo stabil)
  * **Edge Case(s):** Grenzwerte, Null/Empty, Sonderformate, Collections leer vs. null, große Werte, etc.
* **Sehr hohe Abdeckung** der neuen Klasse ist anzustreben (Ziel: nahe 100 % Branch-/Line-Coverage der neuen Klasse),
  mindestens jedoch so, dass die Abdeckungsregel **≥ 80 % der geänderten Logik** sicher erfüllt ist.

### Repo-Stil & technische Vorgaben

* Unit Tests: JUnit 5 + Mockito (falls Mocking erforderlich)
* Keine übermäßigen Integrations-Setups in Unit Tests (kein Spring Context, außer ausdrücklich erforderlich)
* Testnamen sprechend (z. B. `method_shouldDoX_whenConditionY`)
* Assertions präzise (z. B. AssertJ, falls im Repo üblich; ansonsten JUnit Assertions)

---

# 7. Evidenz- und Nachweispflicht

Jede projektspezifische Aussage benötigt:

* **pfad:zeilen**
  oder
* **pfad + Klassen-/Methodennamen + kurzer Codeausschnitt**

Für Inhalte aus Archiv-Artefakten ist Evidenz **nur gültig**, wenn sie aus tatsächlich extrahierten Dateien stammt.

Wenn nicht auffindbar → expliziter Hinweis im Output.

Keine Annahmen ohne Kennzeichnung.
Persistente Annahmen müssen in den Session-State.

---

# 8. Traceability

Jedes Ticket muss eine Matrix liefern:

| Ticket-Anforderung | Geänderte Klassen/Dateien | Betroffene Endpunkte | Tests | Risiken/Annahmen |
| ------------------ | ------------------------- | -------------------- | ----- | ---------------- |

---

# 9. Fehler- & Lückenhandling

## 9.1 Fehlende Artefakte

Wenn z. B. APIs fehlen:

* KI listet exakt, was fehlt
* KI liefert einen Plan, aber keine Implementierung

## 9.2 Nicht vorhandene Strukturen

Wenn der Benutzer auf einen Pfad, Endpunkt oder eine Klasse verweist, die nicht existiert:

* Antwort: „Diese Datei/Struktur ist im gelieferten Scope nicht vorhanden."
* Keine Alternativen, keine Erfindungen

## 9.3 Ambiguitäten

Wenn etwas nicht eindeutig ist:

* minimal notwendige Annahme formulieren
* Annahme explizit markieren
* im Session-State dokumentieren

---

# 10. Build- und Qualitätschecks

Für jede Implementierung:

mvn -B -DskipITs=false clean verify

Erwartungen:

* alle Tests grün
* JaCoCo ≥ 80 % der geänderten Logik
* Checkstyle/Formatter ohne Findings
* keine Wildcard-Imports
* OpenAPI-Contract-Tests grün
* ArchUnit ohne Schichtverletzungen

---

# 11. Output-Struktur für Tickets

Jede Umsetzung besteht aus:

1. **Plan**
2. **Diffs**
3. **Neue Dateien**
4. **Unit-/Slice-/Integrationstests** (inkl. neuer Testklassen für alle neu erstellten produktiven Klassen gemäß 6.5)
5. **How-to-run**
6. **Annahmen & offene Punkte**
7. **Traceability-Matrix**
8. **Evidenzliste**
9. (optional) `changes.patch` + `README-CHANGES.md`

---

# 12. Erweiterbarkeit

Neue Technologien, zusätzliche Phasen oder projektspezifische Regeln
werden ausschließlich durch Ergänzungen in diesem Dokument eingeführt.

Der Master Prompt bleibt unverändert.
README-RULES.md wird lediglich aktualisiert, um neue Inhalte zu referenzieren.

---

# Ende der Datei — rules.md v3.1
