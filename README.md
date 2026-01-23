# Governance & Prompt System – Übersicht

Dieses Repository enthält ein **mehrschichtiges Governance- und Prompt-System**
für KI-gestützte Softwareentwicklung mit Fokus auf **Lead-/Staff-Qualität**,
Nachvollziehbarkeit und Review-Festigkeit.

Das System ist so aufgebaut, dass es **sowohl im reinen Chat-Betrieb**
als auch **repo-aware mit OpenCode** effizient und token-schonend eingesetzt
werden kann.

Dieses README ist **beschreibend**, nicht normativ.
Es erklärt Zweck, Aufbau und Nutzung – es steuert **nicht** das Verhalten der KI.

---

## 1. Zielsetzung

Das System adressiert ein zentrales Problem moderner KI-gestützter Entwicklung:

> Wie erreicht man reproduzierbar **hohe Business- und Testqualität**,
> ohne implizites Wissen, Abkürzungen oder Halluzinationen?

Die Antwort ist eine **klare Trennung von Verantwortung**, ein
**phasenbasierter Workflow** und **harte Gates** für Architektur,
Businesslogik und Tests.

---

## 2. Logische Schichtung (Token-optimiert)

Das System ist bewusst in **drei logische Schichten** aufgebaut.
Diese Schichten sind **keine zusätzlichen Regeln**, sondern eine
**Nutzungs- und Aktivierungsempfehlung**, um Tokenverbrauch und kognitive
Last zu optimieren.

### Layer 1 – Core Governance (Always-On)

**Zweck:**  
Stellt sicher, dass sich die KI korrekt verhält – unabhängig vom Kontext.

**Charakteristik:**
- klein
- immer aktiv
- bestimmt *ob* gearbeitet wird, nicht *wie*

**Inhaltlich umfasst Layer 1:**
- Prioritätenordnung
- Scope-Lock / Repo-First
- Phasenübersicht (1–6)
- Gate-Regeln (wann Code erlaubt ist)
- Session-State-Mechanismus
- Confidence / Degraded / Blocked-Verhalten

**Primäre Dateien:**
- `master.md`
- `SCOPE-AND-CONTEXT.md`

Dieser Layer sollte **immer geladen** sein – sowohl im Chat als auch mit OpenCode.

---

### Layer 2 – Quality & Logic Enforcement (Phase-Scoped)

**Zweck:**  
Erzwingt **Lead-Qualität** für Architektur, Businesslogik und Tests.

**Charakteristik:**
- inhaltlich stark
- nur aktiv, wenn entsprechende Phasen erreicht werden
- größter Qualitätshebel

**Inhaltlich umfasst Layer 2:**
- Business-Rules Discovery (Phase 1.5)
- Test-Quality-Regeln (Coverage-Matrix, Anti-Patterns)
- Business-Rules-Compliance (Phase 5.4)
- Architektur- und Coding-Guidelines

**Primäre Datei:**
- `rules.md`

Dieser Layer wird **phasenabhängig aktiviert**
(z. B. 1.5, 5.3, 5.4) und muss **nicht permanent im Kontext sein**.

---

### Layer 3 – Reference & Examples (Lazy-Loaded)

**Zweck:**  
Dient als **Nachschlagewerk** und zur Absicherung korrekter Interpretation.

**Charakteristik:**
- umfangreich
- viele Beispiele
- nicht entscheidungsrelevant

**Quelle:**
- Beispiel- und Referenzabschnitte innerhalb von `rules.md`

Dieser Layer sollte **nur bei Bedarf**
(Unklarheit, Review, Audit) herangezogen werden.

---

## 3. Einsatz im Chat (ChatGPT, Claude, etc.)

### Empfohlene Nutzung

1. **Initial:**
   - `master.md`
   - `SCOPE-AND-CONTEXT.md`

2. **Arbeiten im Ticket:**
   - Phasen laufen implizit
   - `rules.md` wird erst bei relevanten Gates zugeschaltet

3. **Wichtig:**
   - Businesslogik basiert im Chat ausschließlich auf
     gelieferten Artefakten und expliziten Beschreibungen
   - Externe fachliche Wahrheit kann nicht automatisch erkannt werden

---

## 4. Einsatz mit OpenCode (repo-aware)

### Empfohlene Nutzung

1. **Initial:**
   - OpenCode auf das Repository richten (Repo-Scan)
   - `/master` ausführen

2. **Governance:**
   - `master.md`
   - `rules.md`
   - `SCOPE-AND-CONTEXT.md`
   sind dauerhaft aktiv

3. **Vorteile:**
   - Präzise Business-Rules Discovery aus realem Code
   - Tests und Architektur passen sich dem Repo-Stil an
   - Weniger Fehlannahmen, weniger Review-Reibung

OpenCode ist ein **Qualitätsverstärker**, kein Qualitätsgarant.
Die Qualität entsteht durch die Kombination aus Repo-Kontext **und**
den Gates dieses Systems.

---

## 5. Kommandos & Session-Steuerung (OpenCode)

Dieses Repository definiert drei zentrale Kommandos:

### `/master`
Startet ein neues Vorhaben.
- Lädt die komplette Governance
- Initialisiert den Workflow
- Setzt einen neuen `[SESSION_STATE]`

### `/resume`
Setzt eine bestehende Session **deterministisch** fort.
- Erwartet den letzten `[SESSION_STATE]`
- Keine Re-Discovery
- Keine Neuinterpretation
- Keine neuen Annahmen

### `/continue`
Einheitliche Zustimmung zum Weitermachen.
- Führt **ausschließlich** den Schritt aus,
  der in `SESSION_STATE.Next` definiert ist
- Umgeht keine Gates
- Startet keine neuen Phasen

---

## 6. Rolle der einzelnen Dateien

| Datei                  | Zweck |
|------------------------|-------|
| `master.md`            | Zentrale Steuerung: Phasen, Gates, Session-State |
| `rules.md`             | Technische, architektonische, Test- und Business-Regeln |
| `README-RULES.md`      | Executive Summary (nicht normativ) |
| `SCOPE-AND-CONTEXT.md` | Normative Abgrenzung von Verantwortung & Scope |
| `resume.md`            | OpenCode-Command für kontrollierte Fortsetzung |
| `continue.md`          | OpenCode-Command für einheitliches „Weitermachen“ |
| `ResumePrompt.md`      | Manuelle/Fallback-Variante für Resume ohne Commands |

---

## 7. Für wen ist dieses System gedacht?

**Geeignet für:**
- Senior / Lead / Staff Engineers
- Review-intensive Codebases
- Regulatorische oder audit-kritische Umgebungen
- Teams mit expliziten Architektur- und Qualitätsstandards

**Nicht geeignet für:**
- Prototyping
- exploratives Domain Modeling
- schnelle MVPs ohne Artefakte

---

## 8. Leitprinzip

> Lieber blockieren als raten.  
> Lieber explizit als implizit.  
> Lieber Governance als Geschwindigkeit.

Dieses System ist bewusst konservativ –
und genau deshalb skalierbar und review-fest.

---

_Ende der Datei_
