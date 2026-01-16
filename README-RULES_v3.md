# README-RULES.md

**Version 3.1 — Executive Summary für KI-gestützte Entwicklung**

Dieses Dokument ist die kompakte Zusammenfassung aller verbindlichen Regeln.
Die vollständigen technischen Vorgaben stehen in **rules.md**.
Das operative Verhalten der KI (Phasen, Hybridmodus, Prioritäten, Session-State) wird im **Master Prompt** definiert.

Dieses Dokument enthält keine eigenständigen Regeln.
Es fasst ausschließlich die in rules.md definierten Vorgaben zusammen.
Im Zweifel gilt immer rules.md.

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

## 4. Workflow (Kurzfassung)

Der Standardprozess besteht aus vier Phasen:

### Phase 1 – Regeln laden

* rules.md
* README-RULES.md

### Phase 2 – Repository-Discovery

* Modulbaum
* Schlüsselpakete
* relevante Klassen
* Testinventar
* DB-/Config-Übersicht

**Ausschließlich auf extrahierten Archiv-Inhalten.**
**Keine Interpretation oder Implementierung.**

### Phase 3 – API-Discovery

* Extraktion aller Endpunkte
* Methoden
* Pfade
* DTOs / Schemas
* API-Versionen

**Keine Logikinterpretation, kein Mapping, keine Validierung.**

### Phase 4 – Ticketbearbeitung

* Plan
* komplette Diffs
* neue Dateien
* Tests
* Evidenz
* Traceability
* Session-State-Update

---

## 5. Hybridmodus

Die KI kann flexibel zwischen Phasen wechseln.

### Implizite Aktivierung

* Ticket ohne vorherige Artefakte → direkt Phase 4
* Repository-Upload → Phase 2
* API-Upload → Phase 3

### Explizite Overrides

Die folgenden Kommandos überschreiben alle Standardregeln:

* „Starte direkt in Phase 4.“
* „Überspringe Phase 2.“
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

## 9. Discovery (Phase 2 & 3)

Die KI extrahiert ausschließlich:

* Datei- und Ordnerstrukturen
* relevante Pakete und Klassen
* Testübersichten
* API-Endpunkte und DTOs
* Konfigurationen und Flyway-Skripte

**Keine Interpretation, kein Design, keine Implementierung.**

---

## 10. Session-State

Ab Phase 2 führt der Assistent einen persistenten `SESSION_STATE`-Block.

Jede Antwort ab Phase 2 endet mit:
```
[SESSION_STATE]
Phase: [Nummer]
Repositories:
- Repository A (extrahiert)
- Repository B (Status)
APIs:
- API-Artefakt A (analysiert)
Aktiver Fokusbereich:
- [Beschreibung der relevanten Bereiche]
Offene Entscheidungen:
  - [D1] [Beschreibung]
  - [D2] [Beschreibung]
Blockierende Issues: [Beschreibung] oder "keine"
Nächster Schritt: [Beschreibung]
[/SESSION_STATE]
```

### Regeln

* Nur Inhalte aus gelieferten Artefakten dürfen eingetragen werden
* Repositories/APIs werden als A, B, C, ... durchnummeriert in Reihenfolge des Uploads
* Status kann sein: extrahiert, analysiert, partiell, pending, fehlerhaft
* Aktiver Fokusbereich beschreibt die gerade relevanten Schichten/Module/Bereiche
* Offene Entscheidungen werden mit [D1], [D2], ... nummeriert
* Annahmen müssen explizit markiert sein und
  unter „Offene Entscheidungen“ oder einem expliziten Unterpunkt „Annahmen“ geführt werden
* Der Block wird bei jeder Antwort aktualisiert

---

## 11. Fehlerfälle

Falls Artefakte fehlen oder defekt sind:

* Die KI listet die fehlenden Dateien explizit auf
* Die KI liefert **nur einen Plan**, keine Implementierung
* Es werden **keine** Strukturen, Klassen oder Inhalte erfunden

---

**Ende der Datei — README-RULES.md v3.1**
