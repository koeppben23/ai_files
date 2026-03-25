# Phase 6: Phase 6 in echte Substates zerlegen (v2)

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

### 6.rejected (Transitional)
| Event | Target | Description |
|-------|--------|-------------|
| default | 4 | Return to Phase 4 via /continue |

**Semantics:** Short transitional state, explicit `/continue` required to return to Phase 4.

### 6.complete (Terminal)
- **Terminal state** - no transitions, no mutating commands, no /continue
- No output allowed except read-only summaries

## 4. Command-Änderungen

### Allowed Commands per Substate

| Substate | /implement | /review-decision | /continue |
|----------|-------------|------------------|-----------|
| 6.internal_review | ❌ | ❌ | ✅ |
| 6.presentation | ❌ | ✅ | ❌ |
| 6.execution | ✅ | ❌ | ❌ |
| 6.approved | ✅ | ❌ | ❌ |
| 6.blocked | ✅ | ❌ | ❌ |
| 6.rework | ✅ | ❌ | ❌ |
| 6.rejected | ❌ | ❌ | ✅ |
| 6.complete | ❌ | ❌ | ❌ |

### Explicit Restrictions

**6.complete (Terminal):**
- Blocked: `/continue`, `/ticket`, `/plan`, `/implement`, `/review-decision`
- Blocked types: `persist_evidence`, `start_implementation`, `submit_review_decision`, `advance_routing`
- Output: Read-only summaries only (`review`, `gate_check`)

**6.rejected (Transitional):**
- Blocked: `/review-decision`, `/implementation-decision`
- Requires: Explicit `/continue` to return to Phase 4

**6.blocked:**
- Blocked: `/review-decision`, `/implementation-decision`

## 5. Terminal State Protection

6.complete is **hard protected** against:
- No transitions (empty transitions list in topology)
- No mutating commands (via command_restrictions)
- No /continue (via command_restrictions)
- No output except read-only summaries (via output_policies)

## 6. Messages-Aktualisierung

Messages wurden aktualisiert, um Substate-spezifische Messages zu enthalten:
- 22 neue Transition Messages für Substates
- Messages reflektieren den aktuellen Substate-Kontext
- 6.rejected Message erklärt `/continue`-Requirement

## 7. Testergebnisse

```
tests/architecture/test_topology.py ... 37 passed
tests/architecture/test_messages.py ... 31 passed
tests/architecture/test_command_policy.py ... 42 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_spec_inventory.py ... 18 passed
tests/architecture/test_import_rules.py ... 8 passed
tests/architecture/test_control_plane_guards.py ... 5 passed
tests/architecture/test_repo_identity_guards.py ... 3 passed
tests/architecture/test_phase6_substates.py ... 19 passed (NEGATIVE TESTS)
Total: 196 passed
```

### Neue Prohibition Tests (test_phase6_substates.py)

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestTerminalStateProtection` | 4 | 6.complete terminal protection |
| `TestRejectedStateSemantics` | 4 | 6.rejected transitional semantics |
| `TestSubstateCommandProhibitions` | 3 | Commands not allowed per substate |
| `TestBlockedStateRestrictions` | 1 | 6.blocked restrictions |
| `TestApprovedStateRestrictions` | 2 | 6.approved restrictions |
| `TestExecutionStateRestrictions` | 2 | 6.execution restrictions |
| `TestSubstateConsistency` | 3 | Substate consistency checks |

## 8. Nächste Schritte

1. **Phase 7**: Runtime-Executor bereinigen
2. **Phase 8**: Spec-Validator und Conformance-Checks
3. **Phase 9**: Doku vollständig nachziehen

---

**Nächster Schritt:** Phase 7 - Runtime-Executor bereinigen.
