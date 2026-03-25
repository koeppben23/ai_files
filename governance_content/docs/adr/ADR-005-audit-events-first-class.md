# ADR-005: Audit-Events sind First-Class-Concern

**Status:** Accepted  
**Date:** 2026-03-24  
**Decision Makers:** Architecture Team  
**Related:** audit_events.py, Governance-Architektur

## Context

Ein Governance-System benötigt auditierbare, reproduzierbare Zustandsübergänge. Aktuell sind Audit-Informationspunkte verstreut oder fehlen.

## Decision

**Jede signifikante Aktion erzeugt strukturiertes, maschinenlesbares Audit-Event.**

### Audit-Event-Schema

```python
@dataclass(frozen=True)
class AuditEvent:
    run_id: str                    # Eindeutige Lauf-ID
    timestamp: str                 # ISO-8601
    workspace_fingerprint: str     # Repo-Fingerprint
    phase_before: str              # Phase vor Aktion
    phase_after: str | None        # Phase nach Aktion (null bei Block)
    command: str | None            # User-Command (null bei System)
    event: str                     # Kanonische Event-ID
    transition_id: str | None      # Durchgeführte Transition (null bei Block)
    guard_id: str | None           # Blockierende Guard (null bei Erfolg)
    outcome: AuditOutcome          # Resultat
    error_details: dict | None     # Strukturierte Fehldetails
```

### Audit-Outcomes (Fein differenziert)

| Outcome | Beschreibung | Beispiel |
|---------|--------------|----------|
| `success` | Aktion erfolgreich, Transition durchgeführt | Ticket persisted → advance |
| `blocked_missing_evidence` | Guard blockiert fehlende Evidenz | `/ticket` ohne Ticket-Daten |
| `rejected_by_policy` | Policy blockiert Aktion | `/implement` in falschem State |
| `failed_system_error` | Systemfehler (z.B. Persistence) | Persistenz fehlgeschlagen |

### Audit-Emitter

```python
class AuditEmitter:
    def emit_transition(self, ctx, transition, outcome) -> AuditEvent: ...
    def emit_command_blocked(self, ctx, command_id, reason) -> AuditEvent: ...
    def emit_guard_violation(self, ctx, guard_id, state) -> AuditEvent: ...
    def emit_persistence_error(self, ctx, operation, error) -> AuditEvent: ...
```

## Consequences

- Jeder Kernel-Lauf erzeugt nachvollziehbare Audit-Spur
- Audit-Events sind strukturiert (nicht nur Logs)
- Debugging und Compliance werden vereinfacht
- Fine-grained Outcomes ermöglichen präzise Analyse

## Validation

```python
def test_audit_event_on_transition():
    ctx = ExecutionContext.create()
    result = execute_command(ctx, "ticket", state)
    assert len(ctx.audit_emitter.events) == 1
    event = ctx.audit_emitter.events[0]
    assert event.outcome == "success"
    assert event.phase_before == "4"
    assert event.command == "ticket"

def test_audit_event_on_block():
    state = create_state(phase="4")  # No ticket data
    ctx = ExecutionContext.create()
    with pytest.raises(CommandBlockedError):
        execute_command(ctx, "ticket", state)
    
    event = ctx.audit_emitter.events[-1]
    assert event.outcome == "blocked_missing_evidence"
```
