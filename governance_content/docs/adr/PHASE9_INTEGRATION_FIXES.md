# Phase 9: Integration Fixes

**Status:** Completed  
**Date:** 2026-03-25  
**Review:** Approved with small nits

## 1. Ziel

Systematische Behebung der Cross-Spec-Integrationsprobleme aus dem Gesamtpatch:

1. **Command-Policy /implement Semantik** mit Topology synchronisieren
2. **Reject-Semantik** auf single source of truth reduzieren
3. **6.approved** Default-Transition entfernen (ADR-003)
4. **State 6** (unreachable) entfernen
5. **Legacy-Bridge** auf schmalen Fallback reduzieren

## 2. Änderungen

### 2.1 Topology (topology.yaml)

| Vorher | Nachher | Grund |
|--------|---------|-------|
| `6.approved: default → 6.execution` | `6.approved: implementation_started → 6.execution` | ADR-003: Explizites /implement |
| `6.blocked: default → 6.execution` | `6.blocked: implementation_started → 6.execution` | Konsistent mit /implement |
| `6.rework: default → 6.presentation` | `6.rework: default → 6.presentation` + `implementation_started → 6.execution` | Rerun via /implement |
| `6.presentation: implementation_presentation_ready → 6.execution` | Entfernt | Nicht in Command-Policy produziert |
| `6.presentation: workflow_rejected → 4` | Entfernt | Kein Producer |
| State `6` (unreachable) | Entfernt | Nicht erreichbar |

### 2.2 Guards (guards.yaml)

| Änderung | Grund |
|----------|-------|
| `guard_implementation_presentation_ready` entfernt | Event nicht mehr in Topology |
| `guard_workflow_complete` hinzugefügt | Coverage für workflow_complete Event |

### 2.3 Messages (messages.yaml)

| Entfernt | Grund |
|----------|-------|
| `msg.state.6` | State 6 entfernt |
| `msg.trans.6.default` | State 6 entfernt |
| `msg.trans.6.presentation.implementation_presentation_ready` | Event nicht mehr in Topology |

### 2.4 Runtime (phase_kernel.py)

| Vorher | Nachher |
|--------|---------|
| `is_phase6_*()` nutzten `_detect_phase6_substate_legacy()` direkt | Delegieren an `resolve_phase6_substate()` |
| Bridge war primäre Detection-Logik | Bridge nur noch Fallback |

## 3. Reject-Semantik (Single Source of Truth)

**Ein Ablehnungs-Pfad, kein Doppel:**

| Decision | Event | Substate | Ziel |
|----------|-------|----------|------|
| `/review-decision reject` | `review_rejected` | `6.rejected` | → 4 (replan) |

`workflow_rejected` wurde entfernt (kein Producer, keine Semantik).

## 4. Runtime Bridge

**Vorher (zu breit):**
- Bridge war primäre Detection-Logik
- Stark korreliert mit aktiver Semantik
- `is_phase6_*()` nutzten Bridge direkt

**Nachher (schmal):**
- `resolve_phase6_substate()` ist kanonischer Resolver
- Liest primär `phase6_state` Feld
- Bridge nur noch Fallback wenn `phase6_state` nicht gesetzt
- `is_phase6_*()` delegieren an kanonischen Resolver

## 5. Testergebnisse

```
tests/architecture/ ... 263 passed
```

## 6. Verbleibende Nits

1. **Legacy-Bridge weiter schrumpfen** - klar als temporär markieren, bald löschen
2. **Finaler Message-/Hint-Conformance-Pass** - Messages gegen finale Pfade prüfen
3. **Event-Namensraum vereinheitlichen** - langfristig weiter bereinigen

## 7. Nächste Schritte

- Phase 10: Teststrategie komplett
- Phase 11: Migration und Rollout
- Phase 12: Release-Schnitt
