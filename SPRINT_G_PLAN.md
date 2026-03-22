# Sprint G: Runtime Schema Enforcement

**Status:** ✓ Abgeschlossen  
**Erstellt:** 2026-03-22

## Ziel

Harte Runtime-Validierung an kritischen Dokument-Grenzen einführen, um schleichende Schema-Drift zu verhindern und fail-closed-Verhalten bei schweren Schemafehlern zu garantieren.

---

## Scope / Nicht im Scope

### Im Scope

- **StateDocument** als validierbarer Contract für persistierte Session-State
- **ReviewPayload**, **PlanPayload**, **ReceiptPayload** Strukturen
- Zentrale Validator-Grenzen beim Laden und vor Persistenz
- Fail-closed Validation für kritische Felder

### Nicht im Scope

- Vollständige JSON-Schema-Generierung
- Pydantic/Mypy-Erzwingung im gesamten Codebase
- Schema-Versionierung (kommt später)
- Nicht-kritische Randstrukturen

---

## Phase 1 — StateDocument Validierung

### Ziel

Ein validierbarer Contract für das persistierte State-Dokument mit zentralen Read-/Write-Grenzen.

### Deliverables

1. **StateDocument Schema**
   - Pflichtfelder: `SESSION_STATE`, `metadata`
   - SESSION_STATE-Pflichtfelder: `phase`, `active_gate`
   - Typ-Validierung für bekannte Felder

2. **Validator-Funktion**
   - `validate_state_document(raw: dict) -> ValidationResult`
   - Fail-closed bei schweren Fehlern (fehlende Pflichtfelder)
   - Warnungen bei fehlenden optionalen Feldern

3. **Validator-Grenzen**
   - Beim Laden aus Persistenz
   - Vor kritischen Verarbeitungs-Schritten

### Kritische Pflichtfelder

| Feld | Validierung |
|------|-------------|
| `SESSION_STATE.phase` | Non-empty string, bekannter Token |
| `SESSION_STATE.active_gate` | Non-empty string |
| `SESSION_STATE.status` | Eines von: OK, error, blocked |
| `SESSION_STATE.gates` | dict oder null |

### Tests

- Validator akzeptiert gültiges State-Dokument
- Validator lehnt Dokument ohne SESSION_STATE ab
- Validator lehnt Dokument ohne phase ab
- Validator warnt bei fehlenden optionalen Feldern

---

## Phase 2 — Review-/Plan-/Receipt-Payloads

### Ziel

Struktur-Validierung für die zentralen Payload-Typen mit Fokus auf Gate-Freigabe und Entscheidungs-Felder.

### Deliverables

1. **ReviewPayload Schema**
   - Pflichtfelder: `verdict`, `findings`
   - Typ-Validierung für Entscheidungs-Felder

2. **PlanPayload Schema**
   - Pflichtfelder: `body`, `status`
   - Validierung der Plan-Struktur

3. **ReceiptPayload Schema**
   - Struktur-Validierung für Evidence/Receipt

### Kritische Felder pro Payload

| Payload | Kritische Felder |
|---------|-----------------|
| ReviewPayload | `verdict` (approve/changes_requested/reject), `findings` |
| PlanPayload | `body` (non-empty), `status` |
| ReceiptPayload | `evidence`, `timestamp` |

### Validierungs-Grenzen

- Beim Empfang von LLM-Responses
- Vor Persistenz
- Vor Gate-Freigabe

---

## Phase 3 — Zentrale Validator-Grenzen

### Ziel

Klare Enforcement-Points definieren und implementieren, damit Validierung nicht diffus wird.

### Enforcement-Points

1. **session_reader.py** — Beim Laden aus Persistenz
2. **review_decision_persist.py** — Vor Review-Entscheidungs-Persistenz
3. **phase5_plan_record_persist.py** — Vor Plan-Persistenz
4. **Gate-Freigabe** — Vor Gate-Status-Änderungen

### Fail-Closed Policy

| Fehler-Typ | Verhalten |
|------------|----------|
| Fehlende Pflichtfelder | Block/Exception |
| Unbekannte Feldtypen | Warnung (nicht Block) |
| Fehlende optionale Felder | Warnung |

---

## Done-Contract

### Für Sprint G als abgeschlossen gilt, wenn:

1. ✓ `StateDocument` hat einen validierbaren Contract
2. ✓ `ReviewPayload`, `PlanPayload`, `ReceiptPayload` haben Struktur-Validatoren
3. ✓ Validator-Grenzen sind an den kritischen Punkten implementiert
4. ✓ Fail-closed Policy ist für schwere Fehler implementiert
5. ✓ Neue Unit-Tests für alle Validatoren vorhanden
6. ✓ Bestehende Tests bleiben grün
7. ✓ Keine neue verteilte Validierungslogik neben den zentralen Validatoren

---

## Aufwand

- **Phase 1**: ~2-3 Tage
- **Phase 2**: ~2-3 Tage
- **Phase 3**: ~1-2 Tage
- **Gesamt**: ~5-8 Tage

---

## Risiken

| Risiko | Mitigation |
|--------|------------|
| Zu breiter Scope | Phasen strikt trennen, nicht in einer Phase |
| Performance-Impact | Validierung nur an Grenzen, nicht pro-Feld im Hot-Path |
| Brechende Änderungen | Nur neue Validatoren, bestehender Code bleibt kompatibel |

---

## Vorarbeit

Bestehende Validierungs-Logik identifizieren:
- `session_state_invariants.py` — Bestehende Invarianten-Validierung
- Gate-Evaluators — Haben bereits einige Struktur-Checks
- Schema-Dateien in `assets/schemas/` — Können als Basis dienen

---

## Nächste Schritte

1. Bestehende Validierungs-Logik inventarisieren
2. Phase 1 starten: StateDocument Contract definieren
3. Validator-Funktion implementieren
4. Grenzen implementieren
5. Tests schreiben
