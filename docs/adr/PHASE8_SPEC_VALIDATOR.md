# Phase 8: Spec-Validator und Conformance-Checks (v2)

**Status:** Completed  
**Date:** 2026-03-25  
**Source:** `tests/architecture/test_spec_validator.py`

---

## 1. Ziel

Validiere die interne Konsistenz jeder Spec und die Cross-Spec-Conformance mit expliziter Error/Warning/Gap-Klassifizierung.

## 2. Validation Severity

| Severity | Bedeutung | CI-Blockierung |
|----------|-----------|----------------|
| **ERROR** | Muss gefixt werden vor Merge/Runtime | ✅ Blockiert |
| **WARNING** | Sollte gefixt werden | ❌ Nicht blockierend |
| **TEMPORARY_GAP** | Bewusste Lücke, zeitlich begrenzt | ⚠️ Dokumentiert |

## 3. Validierungs-Regeln

### 3.1 Intra-Spec Validation

| Spec | ERROR Rules | WARNING Rules |
|------|-------------|--------------|
| topology.yaml | unique_state_ids, valid_transition_target, required_fields | unreachable_states, non_terminal_no_transitions |
| guards.yaml | unique_guard_ids, valid_guard_type, valid_composite_refs | - |
| command_policy.yaml | unique_command_ids, required_command_fields, unique_restriction_patterns | - |
| messages.yaml | unique_message_ids, required_message_fields, valid_event_format | - |

### 3.2 Cross-Spec Conformance

| Cross-Ref | Validation |
|-----------|-----------|
| topology ↔ guards | guard_ref → existierende Guard |
| topology ↔ messages | state_id → Topology, event → gültig für State |
| command_policy ↔ topology | allowed_in → existierende States |
| messages ↔ command_policy | Commands → im State erlaubt |

### 3.3 UX Field Validation (ADR-001)

**Verbotene Felder in Topology:**
- State: `active_gate`, `next_gate_condition`, `gate_message`, `instruction`, `presentation_text`
- Transition: `gate_message`, `instruction`, `presentation_text`, `condition_description`
- Metadata: `user_guidance`, `display_name`, `ui_hint`, `icon`, `color`

**Erlaubte strukturelle Metadata:**
- `parent`, `description`, `version`, `schema`

## 4. Testergebnisse

```
tests/architecture/test_spec_validator.py ... 27 passed
tests/architecture/test_topology.py ... 37 passed
tests/architecture/test_messages.py ... 31 passed
tests/architecture/test_command_policy.py ... 42 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_spec_inventory.py ... 18 passed
tests/architecture/test_phase6_substates.py ... 19 passed
tests/architecture/test_phase7_substates.py ... 34 passed
tests/architecture/test_import_rules.py ... 8 passed
tests/architecture/test_control_plane_guards.py ... 5 passed
tests/architecture/test_repo_identity_guards.py ... 3 passed
Total: 257 passed
```

## 5. Neue Tests (v2)

**test_spec_validator.py** enthält 27 Tests:

| Klasse | Tests | Beschreibung |
|--------|-------|--------------|
| `TestTopologyValidation` | 4 | topology.yaml interne Validierung |
| `TestTopologyUXValidation` | 3 | UX-Feld-Validierung auf Raw Spec |
| `TestGuardsValidation` | 4 | guards.yaml interne Validierung |
| `TestCommandPolicyValidation` | 4 | command_policy.yaml interne Validierung |
| `TestMessagesValidation` | 4 | messages.yaml interne Validierung |
| `TestCrossSpecConformance` | 5 | Cross-Spec Conformance |
| `TestValidationSeverityClassification` | 1 | Alle kritischen Regeln sind ERROR |
| `TestValidationResultFormat` | 2 | ValidationResult Format-Konsistenz |

## 6. Key Features v2

1. **Explizite Severity-Klassifizierung**: ERROR/WARNING/TEMPORARY_GAP
2. **Raw Spec Validation**: Prüft verbotene UX-Felder auf Rohdaten
3. **ValidationResult NamedTuple**: Strukturierte Ergebnisse mit Spec/Rule/Message/Location
4. **Severity Enforcement Test**: Garantierte ERROR-Klassifizierung für kritische Regeln

## 7. Nächste Schritte

1. **Phase 9**: Doku vollständig nachziehen
2. **Phase 10**: Teststrategie komplett
3. **Phase 11**: Migration und Rollout

---

**Nächster Schritt:** Phase 9 - Doku vollständig nachziehen.
