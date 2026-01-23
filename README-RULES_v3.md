# README-RULES.md

**Version 3.1 — Executive Summary für KI-gestützte Entwicklung**

Dieses Dokument ist die **kompakte Übersicht** über alle verbindlichen Regeln.
Die vollständigen technischen Vorgaben stehen in **rules.md**.
Das operative Verhalten der KI (Phasen, Hybridmodus, Prioritäten, Session-State) wird im **Master Prompt** definiert.

Dieses Dokument enthält **keine eigenständigen Regeln**.
Es fasst ausschließlich die in rules.md definierten Vorgaben zusammen.
Im Zweifel gilt immer **rules.md** bzw. der **Master Prompt**.

---

## 1. Zielsetzung

### Dieser Prozess ermöglicht KI-gestützte Erstellung von:

* technischen Designs
* Backend-Implementierungen
* API-basierten Integrationen
* Unit-/Slice-/Integrationstests
* Traceability- und Qualitätsnachweisen

Alle Arbeitsschritte folgen einem klar strukturierten, kontrollierten Workflow.

---

## 2. Verbindliche Artefakte

### Archiv-Artefakte

Alle Repositories, APIs oder Sammlungen mehrerer Dateien werden als **Archiv-Artefakte** geliefert.

Beispiele (nicht abschließend):

* ZIP
* TAR
* TAR.GZ / TGZ
* TAR.BZ2 / TAR.XZ
* 7Z
* RAR

**Scope-Lock:**
Die KI darf ausschließlich auf Artefakte zugreifen, die im Ticket bzw. in der aktuellen Session geliefert wurden.

---

## 3. Archiv-Artefakte – verpflichtende Extraktion

Alle gelieferten Archiv-Artefakte werden von der KI **immer real und vollständig extrahiert**.

* Ohne erfolgreiche Extraktion erfolgen **keine** Aussagen über Inhalte, Strukturen oder Klassen.
* Heuristische, erfahrungsbasierte oder rekonstruierte Ableitungen sind unzulässig.
* Ein nicht extrahierbares Archiv gilt als **nicht vorhanden im Sinne des Scope-Lock**.

---

## 4. Workflow (Collapsed View)

Der vollständige Workflow besteht aus **6 Phasen** (inkl. Sub-Phasen und Gates) gemäß **Master Prompt**.
Dieses Dokument zeigt eine **reduzierte 4-Phasen-Sicht** zur schnellen Orientierung.

| Collapsed Phase         | Entspricht Master Prompt           |
| ----------------------- | ---------------------------------- |
| Phase A – Analyse       | Phase 1 + 2                        |
| Phase B – Lösungsdesign | Phase 3A + Phase 3B-1              |
| Phase C – Validierung   | Phase 3B-2 + Phase 4               |
| Phase D – Umsetzung     | Phase 5 (+ optional 5.5) + Phase 6 |

**Erweitert (mit Business-Rules Discovery):**

| Collapsed Phase         | Entspricht Master Prompt                    |
| ----------------------- | ------------------------------------------- |
| Phase A – Analyse       | Phase 1 + *1.5 (optional)* + Phase 2       |
| Phase B – Lösungsdesign | Phase 3A + Phase 3B-1                      |
| Phase C – Validierung   | Phase 3B-2 + Phase 4                       |
| Phase D – Umsetzung     | Phase 5 + *5.4 (falls 1.5 aktiv)* + 5.5 (optional) + 6 |

**Wichtig:**
Alle **Gates, Sub-Phasen (z. B. 3B-1 / 3B-2) und Einschränkungen** gelten vollumfänglich, auch wenn sie hier nicht einzeln dargestellt sind.

**Business-Rules Discovery (Phase 1.5):**
- Automatisch aktiviert bei >30 Klassen + Domain-Layer
- Extrahiert fachliche Regeln aus Code/DB/Tests
- Reduziert Business-Logik-Lücken von ~50% auf <15%
- Details siehe Master Prompt Phase 1.5

---

## 5. Hybridmodus

Die KI kann flexibel zwischen Phasen wechseln.

### Implizite Aktivierung

* Ticket ohne vorherige Artefakte → direkt Phase D
* Repository-Upload → Phase A
* API-Upload → Phase A

### Explizite Overrides

Die folgenden Kommandos überschreiben alle Standardregeln:

* „Starte direkt in Phase D.“
* „Überspringe Phase A.“
* „Arbeite nur mit Backend und ignoriere APIs.“
* „Nutze aktuellen Session-State für erneute Discovery.“

**Explizite Overrides haben stets Vorrang.**

---

## 6. Qualitätsanforderungen (High-Level)

* Java 21, Spring Boot
* Google Java Style
* keine Wildcard-Imports
* Einrückung: 4 Spaces
* strukturiertes Logging, Validierung, Fehlerbehandlung
* Architekturlayer strikt einhalten
* Testabdeckung ≥ 80 % der geänderten Logik
* Für neu erstellte produktive Klassen sind zugehörige Unit-Testklassen (Good/Bad/Edge Cases) verpflichtend (Details in rules.md 6.5)

**Build-Anforderung:**

mvn -B -DskipITs=false clean verify

---

## 7. Output-Anforderungen

Jedes Ticket erzeugt:

1. **Plan** (nummeriert, ausführbar)
2. **Diffs** (max. 300 Zeilen pro Block, max. 5 Dateien pro Antwort)
3. **Neue Dateien** (vollständig)
4. **Unit-/Slice-/Integrationstests**
5. **How-to-Run / Testhinweise**
6. **Traceability-Matrix**
7. **Evidenzliste**
8. **Offene Punkte & Annahmen**

Bei größeren Änderungen zusätzlich:

* changes.patch
* README-CHANGES.md

---

## 8. Scope-Lock & Nicht-Erfinden

* Keine Klassen, Dateien, Endpunkte oder Felder erfinden
* Wenn etwas nicht im gelieferten Material enthalten ist → explizite Meldung
* Allgemeines Wissen darf nur zur Erklärung dienen, nicht zur Projektspezialisierung

---

## 9. Discovery (Phase A)

Die KI extrahiert ausschließlich:

* Datei- und Ordnerstrukturen
* relevante Pakete und Klassen
* Testübersichten
* API-Endpunkte und DTOs
* Konfigurationen und Flyway-Skripte

**Keine Interpretation, kein Design, keine Implementierung.**

---

## 10. Session-State

Der Assistent führt **ab Phase A** einen persistenten **Canonical `[SESSION_STATE]`** gemäß **Master Prompt**.

Dieses README zeigt zusätzlich eine **verkürzte, nicht-normative Lesesicht**.

### 10.1 Canonical Session State (Normativ)

```text
[SESSION_STATE]
Phase=<...> | Confidence=<...> | Degraded=<...>
Facts=[...]
Decisions=[...]
Assumptions=[...]
Risks=[...]
BusinessRules=[
  Inventory:<Anzahl> rules | not-extracted,
  InPlan:<X>/<Total> (<Prozent>%),
  InCode:<X>/<Total> (<Prozent>%),
  InTests:<X>/<Total> (<Prozent>%),
  Gaps:[BR-ID:Beschreibung, ...],
  NewRules:[Beschreibung, ...] | none
]
Gates=[P5:<...>; P5.3:<...>; P5.5:<...>; P6:<...>]
TestQuality=[...]   # nur wenn Phase 5.3 aktiv/ausgeführt
Next=<...>
[/SESSION_STATE]
```

### 10.2 README View (Collapsed, nicht normativ)

```text
[SESSION_STATE – SUMMARY]
Context:
- Repository / Module:
- Ticket / Goal:

Current Phase:
- Phase: <A|B|C|D>
- Gate Status: <OPEN|PASSED|BLOCKED>

Key Decisions:
- …

Open Questions / Blockers:
- …

Next Step:
- …
```

**Regeln:**

* Der Canonical Session State ist **immer maßgeblich**
* Die Summary-Ansicht dient ausschließlich der Lesbarkeit
* Nur Inhalte aus gelieferten Artefakten dürfen eingetragen werden
* Annahmen müssen explizit gekennzeichnet sein
* Der Block wird bei jeder Antwort aktualisiert

---

## 11. Fehlerfälle

Falls Artefakte fehlen oder defekt sind:

* Die KI listet die fehlenden Dateien explizit auf
* Die KI liefert **nur einen Plan**, keine Implementierung
* Es werden **keine** Strukturen, Klassen oder Inhalte erfunden

---

**Ende der Datei — README-RULES.md v3.1**


