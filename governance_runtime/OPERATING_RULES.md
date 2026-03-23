# Governance Runtime v1.0 — Operating Rules

**Version:** 1.0  
**Status:** Active  
**Baseline:** `governance-runtime-v1.0`

---

## Architektur-Vertrag

### State Management

| Regel | Beschreibung |
|-------|-------------|
| **Alias-Quelle** | `state_normalizer.py` ist die EINZIGE Alias-Quelle |
| **Access-Layer** | Entrypoints verwenden `state_accessor.py` |
| **Plan-Reading** | `plan_reader.py` für Plan-Content |
| **Validierung** | Fail-closed an kritischen Grenzen |

### Architektur-Grenzen

| Regel | Beschreibung |
|-------|-------------|
| **Keine neuen Alias-Orte** | Alias-Auflösung NUR in `state_normalizer.py` |
| **Keine App→Infra-Imports** | Application-Layer darf Infrastructure nicht importieren |
| **Keine Legacy-Pfade** | Ohne ausdrückliche Begründung verboten |
| **session_reader.py** | Keine neue Business-Logik dort |

### Allowlist

| Regel | Beschreibung |
|-------|-------------|
| **Wächst nicht** | Allowlist darf nur kleiner werden |
| **Neue Ausnahmen** | Müssen begründet und befristet sein |
| **Monitoring** | Architecture-Tests prüfen täglich |

---

## Monitoring

### Guard Rails

```bash
# Architektur-Tests
pytest tests/architecture/ -v

# Core-Tests
pytest tests/unit/test_state_normalizer.py tests/unit/test_state_accessor.py -v
```

### Beobachtung

- Performance: `normalize_to_canonical()` ~7µs
- Tests: 173 Core-Tests
- Allowlist: 31 Entries (alle begründet)

---

## Bei Bedarf (Trigger)

Neue Sprints/Arbeit nur bei:

| Trigger | Aktion |
|---------|--------|
| Performance-Hotspot | Messen, dann gezielt optimieren |
| Incident/Regression | Analyse, Fix, Regressionstest |
| Neue fachliche Anforderung | Design, dann Implementierung |
| Architektur-Schmerzpunkt | Bewertung, dann gezielter Refactor |

---

## Nicht bei Bedarf

- Vorbeugende große Architekturwellen
- "Sauberer machen" ohne konkreten Schmerzpunkt
- Performance-Optimierung ohne Messung
- Neue Abstraktionsschichten ohne Grund

---

## Baseline

**Tag:** `governance-runtime-v1.0`  
**Commit:** `9d86ac7`  
**Datum:** 2026-03-22

**Erreicht:**
- Kanonisches State-Modell
- state_normalizer als PRIMÄR
- state_accessor als Access-Layer
- state_document_validator für Fail-Closed
- transition_model für explizite Übergänge
- plan_reader als dedizierter Service
- 173 Core-Tests passend
- Architektur dokumentiert

---

## Änderungen an diesem Dokument

Jede Änderung an den Operating Rules erfordert:
1. Architektur-Review
2. Mapping zu einem Trigger oder neuen Grund
3. Dokumentation der Begründung
