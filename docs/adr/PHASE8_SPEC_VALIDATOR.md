# Phase 8: Spec-Validator und Conformance-Checks (v1)

**Status:** Completed  
**Date:** 2026-03-25  
**Source:** `tests/architecture/test_spec_validator.py`

---

## 1. Ziel

Validiere die interne Konsistenz jeder Spec und die Cross-Spec-Conformance.

**Specs:**
- `topology.yaml` - Zustandsmaschine
- `guards.yaml` - Guard/Invariant-Layer
- `command_policy.yaml` - Command-Richtlinien
- `messages.yaml` - Presentation/Messages

## 2. Validierungs-Level

### 2.1 Intra-Spec Validation

| Spec | Tests | Validation |
|------|-------|-----------|
| topology.yaml | 5 | State-IDs eindeutig, Transition-Targets existieren, Pflichtfelder |
| guards.yaml | 4 | Guard-IDs eindeutig, Guard-Typen gültig, Composite-Guards referenzieren existierende Guards |
| command_policy.yaml | 4 | Command-IDs eindeutig, Pflichtfelder, Restrictions eindeutig |
| messages.yaml | 4 | Message-IDs eindeutig, Pflichtfelder, Event-Format gültig |

### 2.2 Cross-Spec Conformance

| Cross-Ref | Validation |
|-----------|-----------|
| topology → guards | guard_ref in Transitions verweist auf existierende Guard |
| topology → messages | state_id existiert in Topology |
| topology ↔ messages | state_id + event Kombination existiert in Topology |
| command_policy ↔ topology | States in allowed_in existieren in Topology |
| messages ↔ command_policy | Commands in Messages sind in Command-Policy erlaubt |

## 3. Testergebnisse

```
tests/architecture/test_spec_validator.py ... 25 passed
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
Total: 255 passed
```

## 4. Neue Tests

**test_spec_validator.py** enthält:

| Klasse | Tests | Beschreibung |
|--------|-------|--------------|
| `TestTopologyIntraSpec` | 5 | topology.yaml interne Validierung |
| `TestGuardsIntraSpec` | 4 | guards.yaml interne Validierung |
| `TestCommandPolicyIntraSpec` | 4 | command_policy.yaml interne Validierung |
| `TestMessagesIntraSpec` | 4 | messages.yaml interne Validierung |
| `TestTopologyGuardsConformance` | 1 | topology ↔ guards Conformance |
| `TestTopologyMessagesConformance` | 2 | topology ↔ messages Conformance |
| `TestCommandPolicyTopologyConformance` | 2 | command_policy ↔ topology Conformance |
| `TestMessagesCommandPolicyConformance` | 1 | messages ↔ command_policy Conformance |
| `TestSpecSchemaVersionConformance` | 2 | Schema-Identifier Konventionen |

## 5. Nächste Schritte

1. **Phase 9**: Doku vollständig nachziehen
2. **Phase 10**: Teststrategie komplett
3. **Phase 11**: Migration und Rollout

---

**Nächster Schritt:** Phase 9 - Doku vollständig nachziehen.
