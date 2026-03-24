# Phase 3: Guard-/Invariant-Schicht extrahieren (v2 - Strict with closed grammar)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/guards.yaml`

---

## 1. Ziel

Extrahiere die Guard-/Invariant-Schicht aus der monolithischen `phase_api.yaml` in eine separate `guards.yaml`-Datei.

Die Guards enthalten **alle** Wachbedingungen und Invarianten - strukturiert gemäß ADR-002 (keine DSL) mit **geschlossener, rekursiv validierter Grammatik**.

## 2. Prinzipien

### 2.1 Geschlossene Grammatik (ADR-002)

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

### 2.2 Metadata-Trennung

| Kategorie | Felder | Erlaubt | Zweck |
|-----------|--------|---------|-------|
| **Runtime-Felder** | `id`, `event`, `condition`, `state_id`, `required_keys` | Ja | Guard-Evaluation |
| **Non-runtime** | `description` | Ja (optional) | Dokumentation |

**Wichtig:** `description` hat **keinen Einfluss** auf Guard-Evaluation. Der Recursive Validator ignoriert es komplett.

### 2.3 Zwei Guard-Typen

| Typ | Beschreibung | Runtime-Felder |
|-----|--------------|----------------|
| **Exit Guards** | State-Verlassen-Invarianten | `state_id`, `required_keys` |
| **Transition Guards** | Transition-Auswahl-Bedingungen | `id`, `event`, `condition` |

### 2.4 Condition Types

| Type | Beschreibung | Operands |
|------|--------------|----------|
| `always` | Immer wahr (Fallback) | - |
| `key_present` | Key existiert und ist truthy | `key` |
| `key_equals` | Key equals value | `key`, `value` |
| `key_missing` | Key fehlt oder ist falsy | `key` |
| `numeric_gte` | Numerischer Vergleich | `key`, `threshold`, `operator` |
| `all_of` | AND composite | `operands[]` |
| `any_of` | OR composite | `operands[]` |

### 2.5 numeric_gte Typ-/Existenzvalidierung

```yaml
# Konstanter Threshold
- type: "numeric_gte"
  key: "plan_record_versions"
  threshold:
    type: "constant"
    value: 1
  operator: "lt"

# Threshold aus State
- type: "numeric_gte"
  key: "phase5_self_review_iterations"
  threshold:
    type: "from_state"
    key: "phase5_max_review_iterations"
  operator: "gte"
```

Validierung:
- `threshold.type` muss `constant` oder `from_state` sein
- `constant.value` muss numerisch sein
- `from_state.key` muss String sein
- `operator` muss einer von: `gte`, `gt`, `lte`, `lt`, `eq`, `neq`

## 3. Erstellte Dateien

### 3.1 `governance_spec/guards.yaml`

Enthält die kanonische Guard-Definition mit 5 Exit Guards und 18 Transition Guards.

### 3.2 `tests/architecture/test_guards.py`

29 Tests für die strikte Guard-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestGuardsStructure` | 4 | Grundlegende Struktur |
| `TestExitGuards` | 5 | Exit Guard Runtime-Felder |
| `TestTransitionGuards` | 6 | Transition Guard Runtime-Felder |
| `TestConditionGrammar` | 8 | Geschlossene Grammatik + Rekursion |
| `TestDescriptionIsNonRuntime` | 3 | Non-runtime Metadata |
| `TestGuardTopologyConsistency` | 3 | Cross-Spec Konsistenz |

## 4. Recursive Condition Validator

Der `validate_condition_recursive()` Validator:

1. Prüft `type` ist in `VALID_CONDITION_TYPES`
2. Prüft nur erlaubte Keys pro Typ (geschlossene Grammatik)
3. Rekursiv für `all_of`/`any_of` operands
4. Validiert `threshold` Struktur für `numeric_gte`
5. Leere `operands` werden abgelehnt

## 5. Testergebnisse

```
tests/architecture/test_guards.py ... 29 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 97 passed
```

## 6. Nächste Schritte

1. **Phase 4**: Command-Policy separat modellieren
2. **Phase 5**: Presentation/Messages herauslösen
3. **Phase 8**: Guard-Ref Cross-Spec Conformance (guard_refs in topology.yaml)

---

**Nächster Schritt:** Command-Policy separat modellieren.
