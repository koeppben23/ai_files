# Scope & Context

Dieses Dokument beschreibt **explizit**, wofür das KI-gestützte Entwicklungs- und Review-System gedacht ist –
und wofür **nicht**. Ziel ist es, Fehlannahmen zu vermeiden, Erwartungen zu kalibrieren
und Governance-Entscheidungen transparent zu machen.

Dieses Dokument ist **normativ**: Abweichungen davon müssen bewusst, explizit und nachvollziehbar erfolgen
(z. B. über Degraded Mode, Overrides oder separate Tickets).

---

## 1. Intended Use (IN SCOPE)

Das System ist **konzipiert und optimiert** für folgende Kontexte:

### 1.1 Technologischer Scope

* ✅ Enterprise Java
* ✅ Spring Boot
* ✅ Maven-basierte Builds
* ✅ Contract-First API Development (OpenAPI)
* ✅ Klassische Backend-Systeme (REST / ggf. GraphQL)

### 1.2 Organisatorischer & Prozess-Scope

* ✅ Strukturierte Ticket-basierte Entwicklung (z. B. Jira)
* ✅ Review-intensive Codebases
* ✅ Mehrstufige Freigabeprozesse (Gates)
* ✅ Regulatorische / audit-kritische Umgebungen
* ✅ Teams mit expliziten Architektur- und Qualitätsstandards

### 1.3 Primäre Systemziele

Das System optimiert **nicht** auf Geschwindigkeit oder Kreativität,
sondern auf:

* Nachvollziehbarkeit
* Determinismus
* Review-Festigkeit
* Contract-Treue
* Reproduzierbarkeit
* Reduktion mechanischer Fehler

---

## 2. Anti-Patterns (EXPLIZIT OUT OF SCOPE)

Das System ist **nicht** dafür ausgelegt und liefert hier bewusst
keine optimalen Ergebnisse:

### 2.1 Entwicklungsstile

* ❌ Prototyping / MVP-Entwicklung
* ❌ Exploratives Domain Modeling
* ❌ "Figure it out as we go"-Tickets
* ❌ Kreative / experimentelle Code-Experimente
* ❌ Rapid Iteration ohne klare Artefakte

### 2.2 Technologischer Scope

* ❌ Non-Java Stacks
* ❌ Frontend-lastige Anwendungen
* ❌ Skript- oder Notebook-basierte Entwicklung
* ❌ Unstrukturierte Monorepos ohne klare Ownership

### 2.3 Erwartungs-Anti-Patterns

* ❌ "Die KI versteht automatisch die Fachdomäne"
* ❌ "Die KI macht Performance-Optimierung"
* ❌ "Die KI erkennt Security-Lücken vollständig"
* ❌ "Die KI ersetzt menschliche Architektur- oder Security-Reviews"

---

## 3. Responsibility Boundaries

Dieses System ist **kein autonomer Entwickler**, sondern ein
hochstrukturierter **Engineering-Assistant mit Governance-Fokus**.

### 3.1 In Scope (Systemverantwortung)

Das System übernimmt Verantwortung für:

* Architektur-Compliance (gemäß Repository-Realität)
* Code-Style & Formatierung
* Contract-Adhärenz (OpenAPI ↔ Code)
* Testpflichten & Coverage-Ziele
* Traceability (Ticket ↔ Code ↔ Tests)
* Evidenzbasierte Aussagen (Scope-Lock)
* Gate-basierte Freigaben (Plan → Review → QA)

### 3.2 Out of Scope (Menschliche Verantwortung)

Folgende Aspekte **müssen** explizit durch Menschen verantwortet werden:

* Fachliche / business-semantische Korrektheit
* Security-Vulnerability-Analyse (OWASP, AuthZ, Threat Modeling)
* Performance-Optimierung & Lasttests
* Algorithmus-Auswahl & Komplexitätsoptimierung
* Domänenspezifische Entscheidungen

Das System kann hier **Hinweise oder Heuristiken liefern**,
übernimmt jedoch **keine Garantie oder Verantwortung**.

## 3.3 Partielle Verantwortung (Heuristiken, keine Garantien)

Das System liefert **Best-Effort-Hinweise** für:

**Security:**
- ⚠️ Offensichtliche Patterns (SQL-Injection-Risiken, Passwörter im Klartext)
- ⚠️ Fehlende Annotationen (@PreAuthorize bei sensiblen Endpunkten)
- ❌ KEINE vollständige OWASP-Analyse
- ❌ KEINE Threat-Modeling-Garantie

**Performance:**
- ⚠️ Strukturelle Risiken (N+1 Queries, fehlende Indices, Nested Loops)
- ⚠️ Transaktions-Boundaries (@Transactional fehlt/falsch)
- ❌ KEINE Lasttest-Validierung
- ❌ KEINE Speicher- oder Latenz-Optimierung

**Status:** HEURISTIC - requires human validation

---

## 4. Konsequenzen für Nutzung & Reviews

### 4.1 Erwartungsklarheit

Wenn das System in einem Kontext eingesetzt wird,
der **außerhalb dieses Scopes** liegt, gelten folgende Regeln:

* Ergebnisse sind als **Best-Effort** zu betrachten
* Degraded / Draft / Blocked Modes sind wahrscheinlicher
* Review-Aufwand verlagert sich bewusst auf Menschen

### 4.2 Kein stillschweigender Scope-Shift

Ein Scope-Wechsel (z. B. Richtung Prototyping oder Exploration)

* ❌ darf **nicht implizit** erfolgen
* ✅ muss explizit gemacht werden (Overrides, Audit-Trail, separate Tickets)

---

## 5. Design-Philosophie (Zusammenfassung)

Leitprinzipien dieses Systems:

* Lieber blockieren als raten
* Lieber explizite Annahmen als implizite Fehler
* Lieber Governance als Geschwindigkeit
* Lieber Review-Festigkeit als Kreativität

Dieses System ist **bewusst konservativ**.
Das ist kein Mangel, sondern eine **Design-Entscheidung**.

---

## 6. Zielbild

Wenn dieses System korrekt eingesetzt wird:

* Reviewer prüfen Fachlichkeit statt Formalien
* Architektur- und Contract-Fehler werden früh eliminiert
* Diskussionen verschieben sich von "Format" zu "Inhalt"
* Code Reviews werden kürzer, fokussierter und reproduzierbar

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# Ende der Datei — SCOPE-AND-CONTEXT.md
