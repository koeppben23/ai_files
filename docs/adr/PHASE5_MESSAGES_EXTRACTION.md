# Phase 5: Presentation/Messages herauslösen

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/messages.yaml`

---

## 1. Ziel

Extrahiere die Presentation/Messages aus der monolithischen `phase_api.yaml` in eine separate `messages.yaml`-Datei.

Die Messages enthalten **alle** UX-Texte und Display-Inhalte - getrennt von der Runtime-Spezifikation.

## 2. Prinzipien

### 2.1 Keine UX-Felder in Runtime-Spec

**In Runtime-Spec (topology.yaml, guards.yaml) verboten:**
- `phase` (Display-Name)
- `active_gate` (Gate-Message)
- `next_gate_condition` (Instruction)

**In messages.yaml erlaubt:**
- `display_name` (statt `phase`)
- `gate_message` (statt `active_gate`)
- `instruction` (statt `next_gate_condition`)

### 2.2 State Messages

```yaml
state_messages:
  - state_id: "5"
    display_name: "5-ArchitectureReview"  # Non-runtime
    gate_message: "Plan Record Preparation Gate"  # Non-runtime
    instruction: "When plan_record_versions < 1, create..."  # Non-runtime
```

### 2.3 Transition Messages

```yaml
transition_messages:
  - transition_key: "5-plan_record_missing"  # Format: <source>-<event>
    gate_message: "Plan Record Preparation Gate"  # Non-runtime
    instruction: "Plan record v1 is required..."  # Non-runtime
```

**Transition Key Format:** `<source_state_id>-<event_name>`

### 2.4 Cross-Spec Konsistenz

- `state_id` in messages muss in topology existieren (oder future state)
- `transition_key` source muss in topology existieren
- Future states from ADR-003 sind erlaubt (6.approved, 6.presentation, etc.)

## 3. Erstellte Dateien

### 3.1 `governance_spec/messages.yaml`

**State Messages (18):**
| State ID | Display Name | Gate Message |
|----------|--------------|--------------|
| 0 | 0-None | Bootstrap Required |
| 1.1 | 1.1-Bootstrap | Workspace Ready Gate |
| 1 | 1-WorkspacePersistence | Persistence Gate |
| ... | ... | ... |
| 5.3 | 5.3-TestQuality | Test Quality Gate |
| 6 | 6-Implementation | Implementation Internal Review |

**Transition Messages (26):**
| Key | Gate Message |
|-----|--------------|
| 1.2-default | Rulebook Load Gate |
| 2.1-business_rules_execute | Business Rules Bootstrap |
| 3A-no_apis | Ticket Input Gate |
| 5-plan_record_missing | Plan Record Preparation Gate |
| 5.3-default | Implementation Internal Review |
| 6-review_changes_requested | Changes Requested |
| ... | ... |

### 3.2 `tests/architecture/test_messages.py`

19 Tests für die strikte Messages-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestMessagesStructure` | 4 | Grundlegende Struktur |
| `TestStateMessages` | 6 | State Message Validierung |
| `TestTransitionMessages` | 7 | Transition Message Validierung |
| `TestMessagesTopologyConsistency` | 2 | Cross-Spec Konsistenz |

## 4. Testergebnisse

```
tests/architecture/test_messages.py ... 19 passed
tests/architecture/test_command_policy.py ... 42 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 162 passed
```

## 5. Nächste Schritte

1. **Phase 6**: Phase 6 in echte Substates zerlegen
2. **Phase 7**: Runtime-Executor bereinigen
3. **Phase 8**: Spec-Validator und Conformance-Checks

---

**Nächster Schritt:** Phase 6 in echte Substates zerlegen.
