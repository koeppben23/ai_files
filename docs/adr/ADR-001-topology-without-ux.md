# ADR-001: Topologie ohne UX-Texte

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** machine_topology.yaml, messages.yaml

## Context

Die aktuelle `phase_api.yaml` mischt Struktur (States, Transitions) mit UX-Texten (`active_gate`, `next_gate_condition`). Das erzeugt eine zweite Wahrheit: Änderungen an Texten erfordern Struktur-Änderungen und umgekehrt.

## Decision

**`machine_topology.yaml` enthält NUR strukturelle Elemente:**

| Erlaubt | Verboten |
|---------|----------|
| `state.id` | `active_gate` |
| `state.parent` (informativ) | `next_gate_condition` |
| `state.is_terminal` | `phase` (Display-Name) |
| `state.start_state_id` | `description` |
| `transition.id` | UX-Texte |
| `transition.source` |  |
| `transition.event` |  |
| `transition.target` |  |
| `transition.guard_ref` |  |

**UX-Texte leben in `messages.yaml`** und werden über Message-IDs referenziert.

## Consequences

- Topologie ist maschinenzentriert und stabil
- UX-Änderungen erfordern keinen Struktur-Change
- `machine_topology.yaml` braucht strikte Validierung (`no_ux_in_topology`)
- Session-Reader nutzt Message-Katalog statt direkter Texte

## Validation

```python
def test_no_ux_in_topology():
    forbidden = ["active_gate", "next_gate_condition", "description"]
    for state in topology.states:
        for field in forbidden:
            assert not hasattr(state, field)
```
