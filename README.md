# Governance & Prompt System – Übersicht

Dieses Repository enthält ein **mehrschichtiges Governance- und Prompt-System** für KI-gestützte Softwareentwicklung mit Fokus auf **Lead-/Staff-Qualität**, Nachvollziehbarkeit und Review-Festigkeit.

Das System ist so aufgebaut, dass es **sowohl im reinen Chat-Betrieb** als auch **repo-aware mit OpenCode** effizient und token-schonend eingesetzt werden kann.

---

## 1. Zielsetzung

Das System adressiert ein zentrales Problem moderner KI-gestützter Entwicklung:

> Wie erreicht man reproduzierbar **hohe Business- und Testqualität**, ohne implizites Wissen, Abkürzungen oder Halluzinationen?

Die Antwort ist eine **klare Trennung von Verantwortung**, ein **phasenbasierter Workflow** und **harte Gates** für Architektur, Tests und Businesslogik.

---

## 2. Logische Schichtung (Token-optimiert)

Das System ist bewusst in **drei logische Schichten** aufgebaut. Diese Schichten sind **keine zusätzlichen Regeln**, sondern eine **Nutzungs- und Aktivierungsempfehlung**, um Tokenverbrauch und kognitive Last zu optimieren.

### Layer 1 – Core Governance (Always-On)

**Zweck:**
Stellt sicher, dass die KI sich korrekt verhält – unabhängig vom Kontext.

**Charakteristik:**

* klein
* immer aktiv
* bestimmt *ob* gearbeitet wird, nicht *wie*

**Inhaltlich umfasst Layer 1:**

* Prioritätenordnung
* Scope-Lock / Repo-First
* Phasenübersicht (1–6)
* Gate-Regeln (wann Code erlaubt ist)
* Session-State-Mechanismus
* Confidence / Degraded / Blocked-Verhalten

**Primäre Dateien:**

* `master.md`
* `SCOPE-AND-CONTEXT.md`

Dieser Layer sollte **immer geladen** sein – sowohl im Chat als auch mit OpenCode.

---

### Layer 2 – Quality & Logic Enforcement (Phase-Scoped)

**Zweck:**
Erzwingt **Lead-Qualität** für Architektur, Businesslogik und Tests.

**Charakteristik:**

* inhaltlich stark
* nur aktiv, wenn entsprechende Phasen erreicht werden
* größter Qualitätshebel

**Inhaltlich umfasst Layer 2:**

* Business-Rules Discovery (Phase 1.5)
* Test-Quality-Regeln (Coverage-Matrix, Anti-Patterns)
* Business-Rules-Compliance (Phase 5.4)
* Architektur- und Coding-Guidelines

**Primäre Datei:**

* `rules.md`

Dieser Layer wird **phasenabhängig aktiviert** (z. B. 1.5, 5.3, 5.4) und muss **nicht permanent im Kontext sein**.

---

### Layer 3 – Reference & Examples (Lazy-Loaded)

**Zweck:**
Dient als **Nachschlagewerk** und zur Absicherung korrekter Interpretation.

**Charakteristik:**

* umfangreich
* viele Beispiele
* nicht entscheidungsrelevant

**Inhaltlich umfasst Layer 3:**

* Codebeispiele
* Musterkataloge
* ausführliche Testbeispiele
* Illustrationen für Business Rules

**Quelle:**

* Beispielabschnitte innerhalb von `rules.md`

Dieser Layer sollte **nur bei Bedarf** (Unklarheit, Review, Audit) herangezogen werden.

---

## 3. Einsatz im Chat (ChatGPT, Claude, etc.)

### Empfohlene Nutzung

1. **Initial:**

   * Master Prompt (Layer 1)
   * ggf. README-RULES (Überblick)

2. **Arbeiten im Ticket:**

   * Phasen laufen implizit
   * Layer 2 wird nur bei relevanten Gates aktiviert

3. **Vorteile im Chat-Betrieb:**

   * Hohe Qualität ohne Repo-Zugriff
   * Deterministisches Verhalten
   * Keine Halluzinationen außerhalb des Scopes

### Einschränkung

Im Chat-Betrieb basiert Businesslogik **ausschließlich auf gelieferten Artefakten und Beschreibungen**. Externe fachliche Wahrheit kann nicht automatisch erkannt werden.

---

## 4. Einsatz mit OpenCode (Repo-aware)

### Empfohlene Nutzung

1. **Initial:**

   * Master Prompt (Layer 1)
   * rules.md verfügbar im Projekt oder global

2. **Automatisch:**

   * Repo-Scan ersetzt große Teile manueller Discovery
   * Business-Rules Discovery (Phase 1.5) wird deutlich präziser

3. **Qualitätsgewinn:**

   * Real existierende Businesslogik wird extrahiert
   * Tests und Architektur passen sich dem Repo-Stil an
   * Weniger Fehlannahmen

### Wichtig

OpenCode ist ein **Qualitätsverstärker**, kein Qualitätsgarant.

Erst die Kombination aus:

* Repo-Kontext **und**
* Gates aus diesem Governance-System

liefert reproduzierbar hohe Ergebnisse.

---

## 5. Rolle der einzelnen Dateien

| Datei                  | Zweck                                                          |
| ---------------------- | -------------------------------------------------------------- |
| `Mmaster.md`           | Zentrale Steuerung: Phasen, Gates, Prioritäten, Session-State  |
| `rules.md`             | Technische, architektonische, testbezogene und Business-Regeln |
| `README-RULES.md`      | Executive Summary, Onboarding, reduzierte Sicht                |
| `SCOPE-AND-CONTEXT.md` | Klare Abgrenzung: was das System kann – und was nicht          |
| `ResumePrompt.txt`     | Kontrollierte Wiederaufnahme laufender Sessions                |

---

## 6. Für wen ist dieses System gedacht?

**Geeignet für:**

* Senior / Lead / Staff Engineers
* Review-intensive Codebases
* Regulatorische oder audit-kritische Umgebungen
* Teams mit klaren Architektur- und Qualitätsstandards

**Nicht geeignet für:**

* Prototyping
* exploratives Domain Modeling
* schnelle MVPs ohne Artefakte

---

## 7. Leitprinzip

> Lieber blockieren als raten.
> Lieber explizit als implizit.
> Lieber Governance als Geschwindigkeit.

Dieses System ist bewusst konservativ – und genau deshalb skalierbar.

---

*Ende der Übersicht*
