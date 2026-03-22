# Governance Runtime — Architektur-Dokumentation

**Version:** 1.0.0  
**Status:** Stabil  
**Letzte Aktualisierung:** 2026-03-22

---

## Überblick

Die Governance Runtime ist ein zustandsbasierter Workflow-Orchestrator für OpenCode-Projekte. Er implementiert ein Phasenmodell (Bootstrap → Intake → Architecture → Review → Implementation → Delivery).

## Kernarchitektur

### State Management

```
┌─────────────────────────────────────────────────────────────┐
│                     SESSION_STATE.json                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 state_normalizer.py                         │
│                 (PRIMÄRE ALIAS-QUELLE)                     │
│                                                             │
│  Kanonisiert Legacy-Aliases:                               │
│  - Phase ↔ phase                                           │
│  - Next ↔ next                                             │
│  - WorkflowComplete ↔ workflow_complete                     │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  state_accessor  │ │  transition_    │ │  state_document │
│  .py             │ │  model.py       │ │  _validator.py  │
│                 │ │                 │ │                 │
│ Access-Layer    │ │ Next-Action     │ │ Fail-Closed    │
│ für Entrypoints │ │ Resolver        │ │ Validierung    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Schichtenarchitektur

| Layer | Verantwortung | Key-Module |
|-------|--------------|------------|
| **Domain** | Geschäftslogik, Gate-Evaluatoren | `gate_evaluator.py`, `phase_state_machine.py` |
| **Application** | Services, Use-Cases | `state_normalizer.py`, `state_accessor.py`, `transition_model.py` |
| **Engine** | Workflow-Orchestrierung | `next_action_resolver.py`, `session_state_invariants.py` |
| **Kernel** | Phasen-Kernel | `phase_kernel.py` |
| **Infrastructure** | I/O, Persistenz, Rendering | `json_store.py`, `snapshot_renderer.py` |
| **Entrypoints** | CLI/API-Schnittstellen | `session_reader.py`, `*_persist.py` |

## Zustandsmodell

### Kanonische Felder

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `phase` | str | Aktuelle Phase (z.B. "6-PostFlight") |
| `next` | str | Nächste Phase (z.B. "5", "6") |
| `active_gate` | str | Aktives Gate |
| `status` | str | Session-Status |
| `mode` | str | Betriebsmodus |
| `Gates` | dict | Gate-Status-Map |

### Alias-Auflösung

**Regel:** Alias-Auflösung NUR in `state_normalizer.py`.

Zulässige Aliases:
- `Phase` ↔ `phase`
- `Next` ↔ `next`
- `WorkflowComplete` ↔ `workflow_complete`
- `Phase5State` ↔ `phase5_state`

## Validierung

### Fail-Closed Policy

```python
validate_state_document(state_doc)  # Wirft bei ungültigem State
validate_review_payload(payload)    # Wirft bei ungültigem Review
validate_plan_payload(payload)      # Wirft bei ungültigem Plan
```

### Übergangsmodell

`transition_model.py` definiert alle gültigen Übergänge:
- Guard-Funktionen prüfen Preconditions
- Next-Action wird explizit berechnet
- Keine impliziten Fallbacks

## Allowlist

**31 Allowlist-Einträge** für Alias-Zugriff (Stand: Sprint K).

### Dauerhaft legitim (14)

- `state_normalizer.py` — PRIMÄR
- `orchestrator.py`, `phase5_normalizer.py`, `state_accessor.py`, `policy_resolver.py`, `transition_model.py` — MIGRATED
- `state_document_validator.py` — SCHEMA
- `session_state_invariants.py`, `phase_kernel.py` — ENGINE/KERNEL
- 5 INFRA-Files

### Review erforderlich (15)

- 10 ENTRYPOINT-Files
- 5 OTHER-Files

## Performance

| Operation | Latenz |
|-----------|--------|
| `normalize_to_canonical()` | ~7µs |
| Zustandsvalidierung | <1ms |

## Testing

```bash
# Architektur-Tests
pytest tests/architecture/

# Unit-Tests
pytest tests/unit/test_state_normalizer.py
pytest tests/unit/test_state_accessor.py
pytest tests/unit/test_transition_model.py
pytest tests/unit/test_state_document_validator.py

# Integration
pytest tests/integration/
```

## Changelog

### v1.0.0 (2026-03-22)

- Sprint A-L abgeschlossen
- Kanonisches State-Modell etabliert
- state_normalizer als PRIMÄRE Alias-Quelle
- state_accessor als Access-Layer
- state_document_validator für Fail-Closed-Validierung
- legacy_compat.py entfernt
- plan_reader.py als dedizierter Service
- Performance: ~7µs pro Normalisierung

---

## Entwicklung

### Neue Features

1. Alias-Auflösung NUR in `state_normalizer.py`
2.state_accessor für Entrypoints verwenden
3. state_document_validator für Fail-Closed-Validierung

### Architektur-Regeln

1. **Alias-Auflösung** → nur in `state_normalizer.py`
2. **Raw State** → nur in ENGINE/KERNEL/INFRA
3. **Validierung** → fail-closed an kritischen Grenzen
4. **Übergänge** → explizit in `transition_model.py`
