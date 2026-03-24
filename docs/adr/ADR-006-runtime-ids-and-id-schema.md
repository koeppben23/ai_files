# ADR-006: Runtime-IDs und ID-Schema

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** machine_topology.yaml, guards.yaml, command_policy.yaml

## Context

IDs für States, Transitions, Guards, Commands und Messages müssen konsistent, stabil und maschinenlesbar sein. Aktuell sind Tokens wie `3A`, `6.presentation` gemischt zwischen Display und Runtime.

## Decision

**Runtime-IDs sind stabil, maschinenlesbar und canonical.**

### V1 Runtime-IDs sind FINAL

Für V1 gelten die kurzen IDs als **kanonische, finale Runtime-IDs**:

```
1, 2, 3, 3A, 4, 5, 6.execution, 6.internal_review, 6.presentation, 
6.approved, 6.blocked, 6.rework, 6.rejected, 6.complete
```

Diese sind **nicht** nur pragmatische Zwischenlösungen, sondern die **explizit festgelegten finalen IDs**.

Optional kann später eine separate Display-Schicht ergänzt werden, **ohne die Runtime-IDs zu ändern**.

### ID-Schema

| Entität | Format | Beispiel |
|---------|--------|----------|
| State | `{number}` oder `{parent}.{qualifier}` | `1`, `6.execution` |
| Transition | `t.{source}.{event_short}` | `t.6.presentation.6.approved` |
| Guard | `g.{name}` | `g.persistence_ready` |
| Command | `{command-name}` | `review-decision`, `implement` |
| Event | `{action}.{detail}` | `review_decision_applied.approve` |
| Message | `{category}.{qualifier}` | `gate.evidence_presentation` |

### ID-Schema-Regeln

1. **Nur alphanumerische Zeichen + `.` und `-`**
2. **Keine Leerzeichen**
3. **Stabil: IDs ändern sich nie ohne Migration**
4. **Kanonisch: Eine Entity = Eine ID**

### Display-Trennung (Erweiterbar, optional)

Display-Trennung kann später ergänzt werden **ohne Runtime-IDs zu ändern**:
```yaml
states:
  - id: "6.execution"               # Runtime-ID (FINAL, stabil)
    display_name: "Phase 6 Execution"  # Optional für UI
```

## Consequences

- IDs sind stabil und revisionssicher
- Migration von Display zu separaten Runtime-IDs möglich
- Validierung kann ID-Schema-Compliance prüfen
- Dokumentation und Code nutzen gleiche IDs

## Validation

```python
def test_id_format_consistent():
    spec = load_topology()
    for state in spec.states:
        assert re.match(r'^[a-zA-Z0-9.]+$', state.id)
    for transition in spec.transitions:
        assert re.match(r'^t\.[a-zA-Z0-9.]+\.[a-zA-Z0-9.]+$', transition.id)

def test_id_uniqueness():
    spec = load_topology()
    state_ids = [s.id for s in spec.states]
    assert len(state_ids) == len(set(state_ids)), "Duplicate state IDs"
```
