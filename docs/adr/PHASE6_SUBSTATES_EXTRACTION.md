# Phase 6: Phase 6 in echte Substates zerlegen (v1)

**Status:** Completed  
**Date:** 2026-03-25  
**Source:** `governance_spec/topology.yaml`

---

## 1. Ziel

Zerlege den monolithischen Phase 6 State in echte Substates gemäß ADR-003.

**Vorher:** Ein einzelner State "6" mit 13 Self-Transitions  
**Nachher:** 8 Substates mit klaren Verantwortlichkeiten

## 2. Substate-Architektur (ADR-003)

```
6 (Container - Delegation Entry Point)
    └── 6.internal_review   (Internal review loop)
    └── 6.presentation      (Evidence presentation)
    └── 6.execution         (Implementation execution)
    └── 6.approved          (Plan approved, ready for /implement)
    └── 6.blocked           (Implementation blocked)
    └── 6.rework            (Rework clarification required)
    └── 6.rejected          (Rejected, return to Phase 4)
    └── 6.complete          (Workflow complete, terminal)
```

## 3. Event-Mapping pro Substate

### 6.internal_review
| Event | Target | Description |
|-------|--------|-------------|
| default | 6.internal_review | Continue review loop |
| implementation_review_pending | 6.internal_review | More iterations needed |
| implementation_review_complete | 6.presentation | Review done, present evidence |

### 6.presentation
| Event | Target | Description |
|-------|--------|-------------|
| default | 6.presentation | Await decision |
| workflow_approved | 6.approved | Plan approved |
| implementation_presentation_ready | 6.execution | Start execution |
| review_changes_requested | 6.rework | Changes needed |
| review_rejected | 6.rejected | Rejected, go to Phase 4 |
| rework_clarification_pending | 6.presentation | Clarification needed |

### 6.execution
| Event | Target | Description |
|-------|--------|-------------|
| default | 6.execution | Continue execution |
| implementation_started | 6.execution | Execution started |
| implementation_execution_in_progress | 6.execution | Execution in progress |
| implementation_accepted | 6.internal_review | Back to review |
| implementation_blocked | 6.blocked | Go to blocked state |
| implementation_rework_clarification_pending | 6.rework | Rework needed |

### 6.approved
| Event | Target | Description |
|-------|--------|-------------|
| default | 6.execution | Start execution |
| workflow_complete | 6.complete | Mark complete |

### 6.blocked
| Event | Target | Description |
|-------|--------|-------------|
| default | 6.execution | Continue after fix |

### 6.rework
| Event | Target | Description |
|-------|--------|-------------|
| default | 6.presentation | Continue to presentation |

### 6.rejected
| Event | Target | Description |
|-------|--------|-------------|
| default | 4 | Return to Phase 4 |

### 6.complete
- Terminal state (no transitions)

## 4. Command-Änderungen

`/implement` ist jetzt erlaubt in:
- `6.approved` - Start implementation
- `6.execution` - Continue/retry implementation  
- `6.blocked` - Rerun after resolving blockers
- `6.rework` - Rerun after clarification

## 5. Messages-Aktualisierung

Messages wurden aktualisiert, um Substate-spezifische Messages zu enthalten:
- 22 neue Transition Messages für Substates
- Messages reflektieren den aktuellen Substate-Kontext

## 6. Testergebnisse

```
tests/architecture/test_topology.py ... 37 passed
tests/architecture/test_messages.py ... 31 passed
tests/architecture/test_command_policy.py ... 42 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_spec_inventory.py ... 18 passed
tests/architecture/test_import_rules.py ... 8 passed
tests/architecture/test_control_plane_guards.py ... 5 passed
tests/architecture/test_repo_identity_guards.py ... 3 passed
Total: 177 passed
```

## 7. Nächste Schritte

1. **Phase 7**: Runtime-Executor bereinigen
2. **Phase 8**: Spec-Validator und Conformance-Checks
3. **Phase 9**: Doku vollständig nachziehen

---

**Nächster Schritt:** Phase 7 - Runtime-Executor bereinigen.
