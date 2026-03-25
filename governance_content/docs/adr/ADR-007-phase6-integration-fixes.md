# ADR-007: Phase 6 Integration Fixes

**Status:** Accepted  
**Date:** 2026-03-25  
**Decision Makers:** Architecture Team  
**Related:** ADR-003, topology.yaml, command_policy.yaml, guards.yaml, messages.yaml

## Context

Review des Gesamt-Patches identifizierte mehrere Cross-Spec-Integrationsprobleme:

1. **Command-Policy produziert Events, die Topology nicht akzeptiert**  
   `/implement` produziert `implementation_started` und `implementation_execution_in_progress`, aber `6.approved`, `6.blocked`, `6.rework` hatten keine Transitionen für diese Events.

2. **workflow_rejected existiert ohne Producer**  
   `workflow_rejected` Event in Topology, aber kein Command produziert es. `review_rejected` ist der korrekte Eventname.

3. **6.approved default-Transition verwässert ADR-003**  
   `6.approved → default → 6.execution` erlaubt impliziten Übergang ohne explizites `/implement`.

4. **State 6 ist unreachable**  
   Base-State `6` war nie direkt erreichbar; alle Pfade führen direkt zu Substates.

5. **Messages für unreachable State 6**  
   `msg.state.6` und `msg.trans.6.default` waren tote Messages.

## Decision

### 1. /implement Semantik synchronisiert

**Vorher:**
```
Command /implement produces:
  - implementation_started
  - implementation_execution_in_progress

Topology akzeptiert aber:
  - 6.approved: default → 6.execution (kein implementation_started)
  - 6.blocked: default → 6.execution (kein implementation_started)
  - 6.rework: default → 6.presentation (kein implementation_started)
```

**Nachher:**
```
6.approved:
  - implementation_started → 6.execution  # Explizit via /implement
  - workflow_complete → 6.complete

6.blocked:
  - default → 6.blocked  # /continue retry
  - implementation_started → 6.execution  # Rerun via /implement

6.rework:
  - default → 6.presentation  # /continue clarification
  - implementation_started → 6.execution  # Rerun via /implement
```

### 2. workflow_rejected entfernt

`workflow_rejected → 4` Transition entfernt. Nur `review_rejected` existiert als Rejection-Event (produziert von `/review-decision`).

### 3. 6.approved braucht explizites /implement

**Vorher:** `6.approved → default → 6.execution` (implizit)  
**Nachher:** `6.approved → implementation_started → 6.execution` (explizit via /implement)

Entspricht ADR-003: "Approval vor Implementierung".

### 4. State 6 entfernt

Base-Container `6` entfernt (war unreachable). Alle Pfade führen direkt zu Substates:
- `5.3/5.4/5.5/5.6 → default → 6.internal_review`
- Substates haben `parent: "6"` für Hierarchie-Info

### 5. Tote Messages entfernt

Entfernt:
- `msg.state.6`
- `msg.trans.6.default`
- `msg.trans.6.presentation.implementation_presentation_ready`

### 6. Guard für workflow_complete hinzugefügt

`guard_workflow_complete` mit `key_present: workflow_complete` Condition.

## Consequences

- Command-Policy und Topology sind jetzt konsistent
- ADR-003 (Approval vor Implementierung) ist sauber umgesetzt
- Keine unreachable States
- Keine Events ohne Producer
- Guard-Coverage für alle Phase-6 Events

## Runtime Bridge Reduktion

Die Legacy-Bridge wurde auf einen schmalen Fallback reduziert:

### Vorher (zu breit)
- `_detect_phase6_substate_legacy()` war die primäre Detection-Logik
- Korreliert stark mit aktiver Semantik
- `is_phase6_*()` Helper nutzten die Bridge direkt

### Nachher (schmal)
- `resolve_phase6_substate()` ist der kanonische Resolver
- Liest primär `phase6_state` Feld
- Bridge nur noch als Fallback wenn `phase6_state` nicht gesetzt
- `is_phase6_*()` delegieren an `resolve_phase6_substate()`

### Reject-Semantik (Single Source of Truth)

Ein Ablehnungs-Pfad, kein Doppel:

| Decision | Event | Substate |
|----------|-------|----------|
| `/review-decision reject` | `review_rejected` | `6.rejected` |

`workflow_rejected` wurde entfernt (kein Producer, keine Semantik).

## Validation

Alle Tests bestehen (263 tests):
```bash
pytest tests/architecture/ -q
```
