# Phase 3: Guard-/Invariant-Schicht extrahieren

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/guards.yaml`

---

## 1. Ziel

Extrahiere die Guard-/Invariant-Schicht aus der monolithischen `phase_api.yaml` in eine separate `guards.yaml`-Datei.

Die Guards enthalten **alle** Wachbedingungen und Invarianten - strukturiert gemäß ADR-002 (keine DSL).

## 2. Prinzipien

### 2.1 Strukturierte Guards (ADR-002)
Guards verwenden deklarative, strukturierte Syntax:
- **Keine DSL** (keine `=>`, `lambda`, `fn()`)
- **Keine Code-Strings** in YAML
- **Nur strukturierte Bedingungen** mit Typ, Operator, Operanden

### 2.2 Zwei Guard-Typen

| Typ | Beschreibung | Quelle |
|-----|--------------|--------|
| **Exit Guards** | Wachbedingungen für State-Verlassen | `exit_required_keys` |
| **Transition Guards** | Bedingungen für Transition-Auswahl | `when` conditions |

### 2.3 Condition Types

| Type | Beschreibung | Beispiel |
|------|--------------|----------|
| `always` | Immer wahr (Fallback) | `type: always` |
| `state_check` | Prüft State-Key | `key: plan_record_versions` |
| `derived` | Abgeleiteter Evaluator | `evaluator: phase5_review_loop_complete` |
| `composite` | Zusammengesetzt (and/or/not) | `operator: or`, `operands: [...]` |

### 2.4 Operator Types

| Operator | Beschreibung |
|----------|--------------|
| `equals`, `not_equals` | Gleichheitsvergleich |
| `truthy`, `falsy` | Wahrheitswert |
| `missing`, `missing_or_empty` | Vorhandensein |
| `less_than`, `greater_than` | Numerisch |
| `contains` | Enthält |
| `and`, `or`, `not` | Logisch (composite) |

## 3. Erstellte Dateien

### 3.1 `governance_spec/guards.yaml`

Enthält die kanonische Guard-Definition:

```yaml
version: 1
schema: opencode.guards.v1

exit_guards:
  - state_id: "1.2"
    description: "Intent committed before proceeding to rulebook load"
    required_keys:
      - "Intent.Path"
      - "Intent.Sha256"
      - "Intent.EffectiveScope"

transition_guards:
  - id: "guard_default"
    event: "default"
    condition:
      type: "always"
  
  - id: "guard_ticket_present"
    event: "ticket_present"
    condition:
      type: "composite"
      operator: "or"
      operands:
        - type: "state_check"
          key: "ticket_recorded"
          operator: "truthy"
        - type: "state_check"
          key: "task_recorded"
          operator: "truthy"
```

### 3.2 `tests/architecture/test_guards.py`

23 Tests für die strikte Guard-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestGuardsStructure` | 4 | Grundlegende Struktur |
| `TestExitGuards` | 5 | Exit Guard Validierung |
| `TestTransitionGuards` | 6 | Transition Guard Validierung |
| `TestGuardConditions` | 5 | Condition Structure (ADR-002) |
| `TestGuardTopologyConsistency` | 3 | Cross-Spec Konsistenz |

## 4. Guard Mapping (Event → Guard)

| Event | Guard ID | Condition Type |
|-------|----------|----------------|
| `default` | `guard_default` | `always` |
| `business_rules_execute` | `guard_business_rules_execute` | `state_check` |
| `no_apis` | `guard_no_apis` | `state_check` |
| `ticket_present` | `guard_ticket_present` | `composite` |
| `plan_record_missing` | `guard_plan_record_missing` | `state_check` |
| `self_review_iterations_pending` | `guard_self_review_iterations_pending` | `derived` |
| `self_review_iterations_met` | `guard_self_review_iterations_met` | `derived` |
| `business_rules_gate_required` | `guard_business_rules_gate_required` | `derived` |
| `technical_debt_proposed` | `guard_technical_debt_proposed` | `state_check` |
| `rollback_required` | `guard_rollback_required` | `state_check` |
| `implementation_*` | `guard_implementation_*` | `derived` |
| `workflow_approved` | `guard_workflow_approved` | `derived` |
| `review_changes_requested` | `guard_review_changes_requested` | `state_check` |
| `rework_clarification_pending` | `guard_rework_clarification_pending` | `derived` |
| `review_rejected` | `guard_review_rejected` | `state_check` |
| `implementation_review_*` | `guard_implementation_review_*` | `derived` |

## 5. Testergebnisse

```
tests/architecture/test_guards.py ... 23 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 91 passed
```

## 6. Nächste Schritte

1. **Phase 4**: Command-Policy separat modellieren
2. **Phase 5**: Presentation/Messages herauslösen
3. **Phase 8**: Guard-Ref Cross-Spec Conformance (guard_refs in topology.yaml)

---

**Nächster Schritt:** Command-Policy separat modellieren.
