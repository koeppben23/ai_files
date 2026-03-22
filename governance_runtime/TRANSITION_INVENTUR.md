# Sprint F: Transition-Inventur

**Status:** Phase 1 - Inventur  
**Erstellt:** 2026-03-22

## Ziel

Alle realen Übergänge (Transitions) im Workflow erfassen als Grundlage für ein explizites Transition-Modell.

---

## Phase 4: Ticket Intake

| Start-Gate | Event/Condition | Guard | Ziel-Phase | Ziel-Gate | next_action |
|------------|-----------------|-------|------------|-----------|------------|
| Ticket Input Gate | - | - | 4 | Ticket Input Gate | `/ticket` |
| Ticket Input Gate | - | - | 4 | - | `/review` (read-only) |
| Plan Record Preparation Gate | versions < 1 | - | 4 | Plan Record Preparation Gate | `/plan` |
| Ticket Input Gate | ticket provided | ready=true | 4 | Scope Change Gate | `/continue` |

---

## Phase 5: Architecture & Quality Gates

| Start-Gate | Event/Condition | Guard | Ziel-Phase | Ziel-Gate | next_action |
|------------|-----------------|-------|------------|-----------|------------|
| Architecture Review Gate | P5-Architecture approved | - | 5.3 | Test Quality Gate | `/continue` |
| Test Quality Gate | P5.3 passed | - | 5.4 | Business Rules Gate | `/continue` |
| Business Rules Gate | p54 status | p54 not compliant | 5.4 | Business Rules Gate | `chat` (blocked) |
| Business Rules Gate | p54 compliant | - | 5.5 | Technical Debt Gate | `/continue` |
| Technical Debt Gate | p55 status | p55 not approved | 5.5 | Technical Debt Gate | `chat` (blocked) |
| Technical Debt Gate | p55 approved | - | 5.6 | Rollback Safety Gate | `/continue` |
| Rollback Safety Gate | p56 status | p56 not approved | 5.6 | Rollback Safety Gate | `chat` (blocked) |
| Rollback Safety Gate | p56 approved | - | 6 | - | `/continue` |

---

## Phase 6: Implementation & Review

| Start-Gate | Event/Condition | Guard | Ziel-Phase | Ziel-Gate | next_action |
|------------|-----------------|-------|------------|-----------|------------|
| Implementation Presentation Gate | - | - | 6 | Implementation Presentation Gate | `/implementation-decision` |
| Implementation Decision | approve | - | 6 | Implementation Started | `/implement` |
| Implementation Decision | reject | - | 6 | Implementation Rework Gate | `chat` (blocked) |
| Implementation Started | - | - | 6 | Implementation Execution | `execute` |
| Implementation Execution | iteration complete | - | 6 | Implementation Self Review | `/continue` |
| Implementation Self Review | iteration < max | - | 6 | Implementation Revision | `/continue` |
| Implementation Revision | revisions done | - | 6 | Implementation Verification | `/continue` |
| Implementation Verification | verified | - | 6 | Implementation Review Complete | `/continue` |
| Implementation Review Complete | - | - | 6 | Evidence Presentation Gate | `/continue` |
| Evidence Presentation Gate | - | - | 6 | Evidence Presentation Gate | `/review-decision` |
| Review Decision | approve | - | 6 | Workflow Complete | `/implement` |
| Review Decision | changes_requested | - | 6 | Rework Clarification Gate | `chat` (blocked) |
| Review Decision | reject | - | 4 | Ticket Input Gate | `chat` (blocked) |
| Rework Clarification Gate | clarification provided | type=scope_change | 4 | Ticket Input Gate | `/ticket` |
| Rework Clarification Gate | clarification provided | type=plan_change | 4 | Plan Record Preparation Gate | `/plan` |
| Rework Clarification Gate | clarification provided | type=other | 6 | Evidence Presentation Gate | `/continue` |
| Workflow Complete | - | - | 6 | Workflow Complete | `/implement` |
| Implementation Blocked | blockers resolved | - | 6 | - | `/implement` |
| Implementation Accepted | - | - | - | - | `delivery` (terminal) |

---

## Rework Classification Routing

| Classification | Ziel-Gate | next_action |
|----------------|-----------|------------|
| `scope_change` | Ticket Input Gate | `/ticket` |
| `plan_change` | Plan Record Preparation Gate | `/plan` |
| `clarification_only` | Evidence Presentation Gate | `/continue` |
| `unknown` | Evidence Presentation Gate | `/continue` |

---

## Status-Based Overrides

| Status | Condition | next_action |
|--------|-----------|------------|
| `error` | - | `/continue` (recovery) |
| `blocked` | - | `/continue` (blocked) |

---

## next_gate_condition Directives

| next_gate_condition contains | next_action |
|-----------------------------|-------------|
| `/review-decision` | `/review-decision` |
| `/implementation-decision` | `/implementation-decision` |
| `run /plan` | `/plan` |
| `run /ticket` | `/ticket` |
| `run /continue` | `/continue` |

---

## Key Gates (Canonical)

```
Ticket Input Gate
Plan Record Preparation Gate
Scope Change Gate
Architecture Review Gate
Test Quality Gate
Business Rules Gate
Technical Debt Gate
Rollback Safety Gate
Implementation Presentation Gate
Implementation Rework Gate
Implementation Started
Implementation Execution
Implementation Self Review
Implementation Revision
Implementation Verification
Implementation Review Complete
Evidence Presentation Gate
Rework Clarification Gate
Workflow Complete
Implementation Blocked
Implementation Accepted
```

---

## Commands (Outputs)

| Command | Kind | Beschreibung |
|---------|------|-------------|
| `/ticket` | normal | Ticket/Task Eingabe |
| `/plan` | normal | Plan Erstellung |
| `/continue` | normal | Phase Fortschritt |
| `/review-decision` | normal | Review Entscheidung |
| `/implementation-decision` | normal | Implementierungs Entscheidung |
| `/implement` | terminal/blocked | Implementierung starten |
| `chat` | blocked | Chat-Interaktion erforderlich |
| `execute` | implementation | Implementierung ausführen |
| `delivery` | terminal | Lieferung abgeschlossen |

---

## Quellen

- `governance_runtime/engine/next_action_resolver.py` - Primary next_action logic
- `governance_runtime/engine/session_state_invariants.py` - Invariant validators
- `governance_runtime/kernel/phase_kernel.py` - Kernel transition selection
- `governance_runtime/domain/phase_state_machine.py` - Phase tokens und Ranks

---

## Nächste Schritte

1. ✓ Transition-Inventur erstellt
2. Transition-Modell definieren (`transition_model.py`)
3. Resolver migrieren
4. Tests hinzufügen
