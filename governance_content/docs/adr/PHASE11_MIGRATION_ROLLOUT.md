# Phase 11: Migration und Rollout (Operational Guidance)

**Status:** Updated 2026-03-25 - Legacy-Bridge entfernt  
**Date:** 2026-03-25

> **WICHTIG:** Die Legacy-Bridge wurde vollständig entfernt.
> Sessions ohne `phase6_state` werden **FAIL-CLOSED** behandelt.
> Alle aktiven Sessions müssen vor dem Deployment migriert sein.

## 1. Ziel

Geordnete Migration von Legacy-State-Machine zur neuen Architektur.

**Wichtig:** Die Legacy-Bridge ist **ENTFERNT**. Das bedeutet:
- Sessions ohne `phase6_state` werfen `ValueError`
- Keine automatische Inferenz mehr
- Alle Sessions müssen `phase6_state` setzen

## 2. Migrationsstrategien

### 2.1 FAIL-CLOSED Verhalten

```
resolve_phase6_substate(state):
  ├── phase6_state present (canonical) → Return directly
  ├── phase6_state present (legacy) → Normalize to canonical
  └── phase6_state missing → ValueError("MISSING_PHASE6_STATE")
```

### 2.2 Legacy-Werte (für laufende Migration)

Diese alten `phase6_state` Werte werden noch akzeptiert und normalisiert:

| Legacy Value | Kanonischer Substate |
|-------------|----------------------|
| `phase6_completed` | `6.complete` |
| `phase6_changes_requested` | `6.rework` |
| `phase6_in_progress` | `6.execution` |
| `completed` | `6.complete` |

### 2.3 Session-Migration (Batch)

```bash
# Script zum Migrieren aller Sessions
python scripts/migrate_phase6_sessions.py --all
```

**Erforderlich vor Deployment:** Alle aktiven Sessions müssen `phase6_state` gesetzt haben.

## 3. Deployment-Vorbereitung

### Pre-Deployment Checkliste

- [ ] Alle Tests grün (6148+ Tests)
- [ ] Batch-Migration aller aktiven Sessions abgeschlossen
- [ ] Monitoring für `ValueError: MISSING_PHASE6_STATE` aktiv
- [ ] Rollback-Prozedur dokumentiert

### Monitoring nach Deployment

| Metric | Alert |
|--------|-------|
| Fehlerrate | > 1% |
| MISSING_PHASE6_STATE errors | > 0 |
| Latenz P99 | > Guardrail |

## 4. Fehlerbehandlung

### MISSING_PHASE6_STATE

```
Fehler: ValueError("MISSING_PHASE6_STATE: Session state is missing 'phase6_state' field.")
Aktion: Session muss migriert werden
```

**Migration durchführen:**
```bash
python scripts/migrate_phase6_sessions.py --session-id=<id>
```

### INVALID_PHASE6_STATE

```
Fehler: ValueError("INVALID_PHASE6_STATE: Unknown phase6_state value '...'")
Aktion: Ungültigen Wert korrigieren
```

## 5. Checkliste

### Pre-Rollout
- [x] Alle Tests grün
- [ ] Batch-Migration aller Sessions
- [ ] Monitoring konfiguriert

### Post-Rollout
- [ ] Monitoring-Review nach 24h
- [ ] Keine MISSING_PHASE6_STATE Fehler
