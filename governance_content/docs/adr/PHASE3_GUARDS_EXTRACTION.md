# Phase 3: Guard-/Invariant-Schicht extrahieren (v3 - Unified model)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/guards.yaml`

---

## 1. Ziel

Extrahiere die Guard-/Invariant-Schicht aus der monolithischen `phase_api.yaml` in eine separate `guards.yaml`-Datei.

**Unified Guard Model:** Exit Guards und Transition Guards teilen eine gemeinsame Struktur mit `guard_type` Attribut.

## 2. Prinzipien

### 2.1 Unified Guard Model

Alle Guards teilen eine gemeinsame Struktur:

```yaml
guard:
  id: string                    # Required, unique
  guard_type: "exit" | "transition"  # Required
  target: string                # Required for exit guards (state_id)
  event: string                 # Required for transition guards
  condition: ConditionNode      # Required
  attributes:                   # Optional, non-runtime metadata
    description: string         # Human-readable intent
    fail_mode: "fail_closed" | "block"  # Failure behavior
    contract_ref: string        # Reference to contract/requirement
```

### 2.2 Keine zwei Guard-Klassen

`guard_type` unterscheidet die **Semantik**, nicht die **Struktur**:

| guard_type | Semantik | Required Fields |
|------------|----------|-----------------|
| `exit` | State-Verlassen-Invarianten | `target` (state_id) |
| `transition` | Transition-Auswahl-Bedingungen | `event` |

Beide teilen:
- Gleiche Condition-Grammatik
- Gleiche attributes Struktur
- Gleichen Recursive Validator

### 2.3 Geschlossene Grammatik (ADR-002)

Die Guard-Grammatik ist **geschlossen** und wird **rekursiv validiert**:

```
ConditionNode = 
  | { type: "always" }
  | { type: "key_present", key: string }
  | { type: "key_equals", key: string, value: any }
  | { type: "key_missing", key: string }
  | { type: "numeric_gte", key: string, threshold: ThresholdNode, operator: string }
  | { type: "all_of", operands: ConditionNode[] }
  | { type: "any_of", operands: ConditionNode[] }

ThresholdNode =
  | { type: "constant", value: number }
  | { type: "from_state", key: string }
```

### 2.4 Strikte Baumvalidierung

Der Recursive Validator prüft:

| Check | Beschreibung |
|-------|--------------|
| Empty dict | `{}` wird abgelehnt |
| Missing type | `{"key": "foo"}` wird abgelehnt |
| Unknown type | `{"type": "unknown"}` wird abgelehnt |
| Unknown keys | `{"type": "always", "extra": "field"}` wird abgelehnt |
| Missing required keys | `{"type": "key_present"}` wird abgelehnt |
| Empty operands | `{"type": "all_of", "operands": []}` wird abgelehnt |
| Non-dict operands | `{"type": "all_of", "operands": ["str"]}` wird abgelehnt |
| Empty string keys | `{"type": "key_present", "key": ""}` wird abgelehnt |
| Invalid threshold | `{"type": "numeric_gte", "threshold": {"type": "unknown"}}` wird abgelehnt |
| Non-numeric constant | `{"type": "numeric_gte", "threshold": {"type": "constant", "value": "str"}}` wird abgelehnt |
| Max recursion depth | Tiefe > 10 wird abgelehnt |

## 3. Erstellte Dateien

### 3.1 `governance_spec/guards.yaml`

Enthält 26 Guards (5 exit + 21 transition) in einheitlicher Struktur.

### 3.2 `tests/architecture/test_guards.py`

33 Tests für die strikte Guard-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestGuardsStructure` | 4 | Grundlegende Struktur |
| `TestGuardModel` | 7 | Unified Guard Model |
| `TestConditionGrammar` | 2 | Geschlossene Grammatik |
| `TestConditionNegative` | 18 | Negative Tests (kaputte Bäume) |
| `TestGuardTopologyConsistency` | 3 | Cross-Spec Konsistenz |

## 4. Testergebnisse

```
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 101 passed
```

## 5. Nächste Schritte

1. **Phase 4**: Command-Policy separat modellieren
2. **Phase 5**: Presentation/Messages herauslösen
3. **Phase 8**: Guard-Ref Cross-Spec Conformance (guard_refs in topology.yaml)

---

**Nächster Schritt:** Command-Policy separat modellieren.
