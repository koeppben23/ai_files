# Phase 10: Teststrategie komplett

**Status:** Completed  
**Date:** 2026-03-25

## 1. Ziel

Vollständige Teststrategie für das State-Machine-Refactoring dokumentieren.

## 2. Testlandschaft

### 2.1 Architecture Tests (268 Tests)

| Datei | Tests | Abdeckung |
|-------|-------|-----------|
| `test_topology.py` | 57 | Topology Schema, Substates, Cross-Spec |
| `test_guards.py` | 35 | Guard-Modell, Condition-Typen |
| `test_command_policy.py` | 44 | Command → Event Mapping |
| `test_messages.py` | 32 | Message-Struktur, State/Event Binding |
| `test_spec_inventory.py` | 18 | Spec-Klassifikation |
| `test_phase6_substates.py` | 21 | Phase 6 Substate Prohibitions |
| `test_phase7_substates.py` | 37 | Runtime Substate Detection |
| `test_spec_validator.py` | 24 | Spec-Validator Conformance |
| `test_golden_flows.py` | 32 | Golden Flows, Adversarial, Invarianten |

### 2.2 Conformance Tests (472 Tests)

| Kategorie | Tests | Beschreibung |
|-----------|-------|--------------|
| Contract Alignment | 9 | Root-Verzeichnis, Governance-Struktur |
| Wiring Conformance | 50 | Binding-Pfade, Schema-Validierung |
| Log Path | 12 | Workspace-Logs, Schema-Locations |
| Final Sweep | variiert | Root-Bridges, Governance-Directories |

### 2.3 Integration Tests

| Kategorie | Tests | Beschreibung |
|-----------|-------|--------------|
| Governance Flow | variiert | End-to-End Flow-Äquivalenz |
| Installer E2E | variiert | Bootstrap, Installation |

## 3. Teststrategie

### 3.1 Test-Kategorien

| Kategorie | Ziel | Beispiele |
|-----------|------|-----------|
| Happy Path | Korrektes Verhalten | Happy-State-Transitions, gültige Commands |
| Negative | Fehlerbehandlung | Invalid Events, fehlende Felder |
| Corner Cases | Grenzfälle | Leere States, unbekannte Events |
| Conformance | Spec-Einhaltung | YAML-Schema, Cross-Ref-Validierung |
| Regression | Bestehendes Verhalten | Golden-Flow-Äquivalenz |

### 3.2 Phase 6 Test-Hierarchie

```
Phase 6 Substates
├── Topology Tests
│   ├── Schema-Validierung
│   ├── Reachability
│   └── Substate-Hierarchie
├── Guard Tests
│   ├── Condition-Typen
│   └── Guard-Referenzen
├── Command Policy Tests
│   ├── /implement in 6.approved
│   ├── /implement in 6.blocked
│   └── /implement in 6.rework
├── Runtime Tests
│   ├── resolve_phase6_substate()
│   ├── is_phase6_*() Helpers
│   └── Legacy Bridge
└── Spec Validator
    ├── Forbidden Fields
    ├── Cross-Spec Conformance
    └── Message/Command/State Alignment
```

### 3.3 Critical Test Cases

| Test | Zweck | Severity |
|------|-------|----------|
| `test_6_approved_requires_explicit_implement` | ADR-003 Enforce | CRITICAL |
| `test_no_workflow_rejected_event` | Single Reject Source | CRITICAL |
| `test_phase6_state_container_removed` | No Dead States | HIGH |
| `test_blocked_has_recovery_path` | blocked/rework Härtung | HIGH |
| `test_rework_has_clarification_path` | blocked/rework Härtung | HIGH |
| `test_forbidden_ux_fields_rejected` | ADR-001 Enforce | HIGH |

## 4. Test Execution

### 4.1 Schnelle Suite (Architecture)
```bash
pytest tests/architecture/ -q
# Erwartet: 268 passed
```

### 4.2 Conformance Suite
```bash
pytest tests/conformance/ -q
# Erwartet: 472 passed
```

### 4.3 Vollständige Suite
```bash
pytest tests/ -q
# Erwartet: 6100+ passed, 6 skipped
```

## 5. Coverage-Ziele

| Komponente | Ziel | Status |
|------------|------|--------|
| Specs (topology, guards, command_policy, messages) | 100% | ✅ |
| Phase 6 Substates | 100% | ✅ |
| Spec Validator | 100% | ✅ |
| Runtime Kernel | 90% | ⚠️ |
| Legacy Bridge | Dokumentiert | ⚠️ |

## 6. Golden Flows (Phase 10.1)

### 6.1 Definierte Golden Flows

| Name | Beschreibung | Schritte |
|------|-------------|----------|
| happy_path_approval_to_complete | Approval → Implement → Complete | 4 |
| reject_and_replan | Reject → Return to Phase 4 | 3 |
| rework_flow | Changes Requested → Rework → Re-presentation | 3 |
| blocked_recovery | Blocked → Recovery → Continue | 3 |
| rework_with_rerun | Rework → Rerun Implementation | 3 |
| review_readonly_no_mutation | /review is read-only | 1 |

### 6.2 Golden Flow Eigenschaften

- **Deterministisch**: Gleiche Eingabe → gleiche Ausgabe
- **Kanonisch**: Events kommen aus definierter Liste
- **Terminal**: Endet in 6.complete oder stabilem Zustand
- **Referenz**: Dient als Ground Truth für Migration

### 6.3 Adversarial Tests

Adversarial Tests prüfen fail-closed Verhalten:

| Test | Erwartung |
|------|-----------|
| implement_in_presentation_blocked | FAIL |
| implement_in_rejected_blocked | FAIL |
| mutate_terminal_state | FAIL |
| implement_from_internal_review_blocked | FAIL |

## 7. Architektur-Invarianten (Metamorphe Tests)

### 7.1 Definierte Invarianten

| Invariante | Beschreibung |
|------------|-------------|
| Same State Same Transitions | Gleicher Zustand + Event = gleiche Transition |
| Terminal States Immutability | 6.complete hat keine mutierenden Transitionen |
| Review Read-Only | /review mutiert den State nicht |
| Approval Before Implementation | 6.presentation → 6.execution ohne 6.approved verboten |

## 8. Legacy-Bridge als Transitional

Die Legacy-Bridge (`_detect_phase6_substate_legacy`) ist als **TRANSITIONAL** markiert:

- WIRD NACH Migration entfernt
- Nur für Sessions ohne `phase6_state` Feld
- NICHT als normaler Happy Path

## 9. Performance Guardrails

Performance-Tests nutzen **relative Regression-Checks**, keine absoluten ms-Werte:

| Check | Typ |
|-------|-----|
| Spec Load | Guardrail (nicht absolut) |
| Transition Resolve | Guardrail (nicht absolut) |

## 10. Follow-up

- Legacy-Bridge Coverage nach Bridge-Entfernung eliminieren
- E2E/Golden-Flow Tests nach Migration
- blocked/rework Semantik-Tests nach Monitoring
