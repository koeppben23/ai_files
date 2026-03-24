# ADR-004: Command → Event Übersetzung ist kanonisch

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** command_policy.yaml, audit_events

## Context

Aktuell sind Commands (User-Input) und Events (Machine-Internal) nicht klar getrennt. Das führt dazu, dass:
- Runtime-Orchestrierung und Machine-Semantik verwischen
- Audit-Auswertung erschwert wird
- Testbarkeit leidet

## Decision

**Command → Event Mapping ist explizit, kanonisch und maschinenlesbar:**

### Klassen von Events

| Klasse | Beschreibung | Beispiel |
|--------|--------------|----------|
| User Command | Nutzer-Input über Command | `/review-decision approve` |
| System Event | Kernel-interne Ereignisse | `iteration_complete`, `max_iterations_reached` |

### Mapping in `command_policy.yaml`

```yaml
commands:
  - id: "review-decision"
    event_mapping:                    # Einfache Mapping
      approve: "review_decision_applied.approve"
      changes_requested: "review_decision_applied.changes_requested"
      reject: "review_decision_applied.reject"
      
  - id: "ticket"
    event_mapping: "ticket_persisted"  # Direkte Mapping
    
  - id: "review"
    event_mapping: null                # Read-only, kein Event
    
  - id: "continue"
    event_mapping: "determined_by_state"  # Spezialfall

system_events:
  - id: "iteration_complete"
    source: "kernel"
  - id: "max_iterations_reached"
    source: "kernel"
```

### Mapping-Implementierung

```python
class CommandEventMapper:
    def map(self, command_id: str, state: str, params: dict) -> str | None:
        """Gibt Event-ID zurück oder None (read-only)."""
        cmd = self.policy.get_command(command_id)
        if cmd.classification == "READ-ONLY":
            return None
        if cmd.event_mapping == "determined_by_state":
            return self._determine_event_by_state(state, params)
        if isinstance(cmd.event_mapping, dict):
            decision = params.get("decision")
            return cmd.event_mapping.get(decision)
        return cmd.event_mapping

    def is_system_event(self, event: str) -> bool:
        """Unterscheidet User-Commands von System-Events."""
        system_events = {e.id for e in self.policy.system_events}
        return event in system_events
```

## Consequences

- Commands sind User-Input, Events sind Machine-Internal
- Mapping ist maschinenlesbar und testbar
- Audit kann klar zwischen User-Aktionen und System-Ereignissen unterscheiden
- `determined_by_state` ist expliziter Spezialfall, nicht versteckte Logik

## Validation

```python
def test_command_event_mapping():
    mapper = CommandEventMapper(policy)
    assert mapper.map("review-decision", "6.presentation", {"decision": "approve"}) == "review_decision_applied.approve"
    assert mapper.map("review", "4", {}) is None  # Read-only

def test_system_vs_user_events():
    mapper = CommandEventMapper(policy)
    assert mapper.is_system_event("iteration_complete") is True
    assert mapper.is_system_event("review_decision_applied.approve") is False
```
