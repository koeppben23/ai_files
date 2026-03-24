# Phase 4: Command-Policy separat modellieren

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/command_policy.yaml`

---

## 1. Ziel

Extrahiere die Command-Policy aus der monolithischen `phase_api.yaml` in eine separate `command_policy.yaml`-Datei.

Die Command-Policy enthält:
- Welche Commands in welchen States erlaubt sind
- Welche Output-Klassen erlaubt/verboten sind
- Plan-Discipline Regeln

## 2. Prinzipien

### 2.1 Command Definition

```yaml
command:
  id: string              # Required, unique, starts with "cmd_"
  command: string         # Required, starts with "/"
  allowed_in: "*" | string[]  # Required: "*" or list of state IDs
  mutating: boolean       # Required: affects state or not
  behavior:               # Required: what the command does
    type: string          # One of: advance_routing, review_readonly, etc.
  description: string     # Non-runtime: human-readable
  constraints: string[]   # Non-runtime: additional constraints
```

### 2.2 Output Policy

```yaml
output_policy:
  state_id: string                    # Target state
  allowed_output_classes: string[]    # What can be produced
  forbidden_output_classes: string[]  # What is forbidden
  plan_discipline:                    # Optional: plan-specific rules
    first_output_is_draft: boolean
    draft_not_review_ready: boolean
    min_self_review_iterations: int
```

### 2.3 Phase Output Policy Map

Maps phases to their output policies. Only phases with explicit restrictions are listed.
Phases not in the map have unbounded output (no restrictions).

## 3. Erstellte Dateien

### 3.1 `governance_spec/command_policy.yaml`

Enthält:
- 8 Commands (2 universal + 6 state-specific)
- 1 Output Policy (Phase 5)
- 5 Phase Output Policy Map entries

### 3.2 `tests/architecture/test_command_policy.py`

22 Tests für die strikte Command-Policy-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestCommandPolicyStructure` | 3 | Grundlegende Struktur |
| `TestCommands` | 7 | Command Definitionen |
| `TestOutputPolicies` | 8 | Output Policy Validierung |
| `TestPhaseOutputPolicyMap` | 3 | Phase Mapping |
| `TestCommandTopologyConsistency` | 2 | Cross-Spec Konsistenz |

## 4. Commands

| Command | Type | Mutating | Allowed In |
|---------|------|----------|------------|
| `/continue` | advance_routing | Yes | All (*) |
| `/review` | review_readonly | No | All (*) |
| `/ticket` | persist_evidence | Yes | 4 |
| `/plan` | persist_evidence | Yes | 4, 5 |
| `/implement` | start_implementation | Yes | 6 (Ist-Zustand) |
| `/review-decision` | submit_review_decision | Yes | 6 |
| `/implementation-decision` | submit_review_decision | Yes | 6 |

## 5. Output Policy (Phase 5)

**Allowed:**
- plan, review, risk_analysis, test_strategy
- gate_check, rollback_plan
- review_questions, consolidated_review_plan

**Forbidden:**
- implementation, patch, diff, code_delivery

**Plan Discipline:**
- first_output_is_draft: true
- draft_not_review_ready: true
- min_self_review_iterations: 1

## 6. Testergebnisse

```
tests/architecture/test_command_policy.py ... 22 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 123 passed
```

## 7. Nächste Schritte

1. **Phase 5**: Presentation/Messages herauslösen
2. **Phase 6**: Phase 6 in echte Substates zerlegen

---

**Nächster Schritt:** Presentation/Messages herauslösen.
