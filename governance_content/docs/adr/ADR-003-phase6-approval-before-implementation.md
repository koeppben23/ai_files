# ADR-003: Phase 6 - Approval vor Implementierung

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** Phase 6 Substates, command_policy.yaml

## Context

Aktuell liegt `/implement` und `/review-decision` potenziell im selben Gate-Moment (`6.presentation`). Das ist semantisch unscharf:

- Wird erst approve gegeben und dann /implement erlaubt?
- Oder ist /implement Teil desselben Review-/Approval-Fensters?

Für Auditierbarkeit und klare Verantwortlichkeit muss dies getrennt sein.

## Decision

**Phase 6 hat expliziten Approval-Zustand (`6.approved`) zwischen Decision und Implement:**

```
6.presentation → /review-decision approve → 6.approved → /implement → 6.execution
```

### State-Übergänge

| Source | Event | Target |
|--------|-------|--------|
| `6.presentation` | `workflow_approved` | `6.approved` |
| `6.presentation` | `review_changes_requested` | `6.rework` |
| `6.presentation` | `review_rejected` | `6.rejected` |
| `6.approved` | `implementation_started` | `6.execution` |
| `6.approved` | `workflow_complete` | `6.complete` |
| `6.execution` | `implementation_started` | `6.execution` (self-loop) |
| `6.execution` | `implementation_blocked` | `6.blocked` |
| `6.blocked` | `implementation_started` | `6.execution` |
| `6.rework` | `default` | `6.presentation` |
| `6.rework` | `implementation_started` | `6.execution` |

**Hinweis:** `/implement` produziert `implementation_started` Event, das die explizite Transition auslöst.

### Command-Policy

```yaml
- id: "review-decision"
  allowed_states: ["6.presentation"]
  
- id: "implement"
  allowed_states: ["6.approved"]  # NICHT 6.presentation
```

## Consequences

- Approval ist eigener, auditierbarer Transition-Punkt
- `/implement` aus `6.presentation` ist `CommandBlockedError`
- Klarere Verantwortungstrennung: Decision vs. Ausführung
- Golden Flows müssen angepasst werden

## Migration

- `6.presentation` bleibt für Decision
- Neuer State `6.approved` als Brücke zu `6.execution`
- Bestehende Golden Flows aktualisieren

## Validation

```python
def test_implement_blocked_before_approval():
    state = create_state(phase="6.presentation")
    with pytest.raises(CommandBlockedError):
        execute_command("implement", state)

def test_approval_enables_implementation():
    state = create_state(phase="6.approved", workflow_approved=True)
    result = execute_command("implement", state)
    assert result.new_phase == "6.execution"
```
