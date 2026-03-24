# Phase 5: Presentation/Messages herauslösen (v2 - Strict with cross-ref validation)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/messages.yaml`

---

## 1. Ziel

Extrahiere die Presentation/Messages aus der monolithischen `phase_api.yaml` in eine separate `messages.yaml`-Datei.

**Key Features:**
- Stable message IDs for cross-spec conformance
- Defined context contract (allowed keys, fallbacks)
- Presentation-only layer (no runtime fields)
- Command conformance checks (hints match allowed commands)

## 2. Prinzipien

### 2.1 Stable Message IDs

```yaml
state_messages:
  - id: "msg.state.5"        # Stable ID format: msg.state.<state_id>
    state_id: "5"
    ...

transition_messages:
  - id: "msg.trans.5.default"  # Stable ID format: msg.trans.<source>-<event>
    transition_key: "5-default"
    ...
```

### 2.2 Context Contract

Defines allowed context keys and fallback rules:

```yaml
context_contract:
  allowed_keys:
    - "state_id"          # Current state ID
    - "event"             # Triggering event name
    - "command"           # Command that triggered
    - "iteration_count"   # For review loops
    - "max_iterations"    # Maximum iterations
    - "required_evidence" # Required evidence keys
  fallback_rules:
    missing_state_id: "ERROR: state_id context required"
    unknown_key: "ERROR: unknown context key '{key}'"
```

### 2.3 Presentation-Only Layer

Messages contain NO runtime fields. Tests verify:
- No `next`, `route_strategy`, `transitions`, `terminal` (state messages)
- No `next`, `source`, `when` (transition messages)
- No `condition`, `guard_ref`, `exit_required_keys` (no guard fields)
- No `allowed_in`, `mutating`, `produces_events` (no command fields)

### 2.4 Command Conformance

Instructions that reference commands are validated against command_policy:
- `/continue`, `/review` are universal (always allowed)
- For Phase 6, commands for `6.approved`/`6.presentation` are recognized
- Cross-ref ensures no drift between messages and command policy

### 2.5 Category Definitions

| Category | Purpose | Example |
|----------|---------|---------|
| `display_name` | Pure state identifier for UI | "5-ArchitectureReview" |
| `gate_message` | Current gate/status display | "Plan Record Preparation Gate" |
| `instruction` | Next action hints | "Use /continue to proceed" |

## 3. Erstellte Dateien

### 3.1 `governance_spec/messages.yaml`

**State Messages (18):**
- Stable IDs: `msg.state.<state_id>`
- Display name, gate message, instruction per state

**Transition Messages (27):**
- Stable IDs: `msg.trans.<source>-<event>`
- Gate message, instruction per transition

**Context Contract:**
- 6 allowed keys
- 3 fallback rules
- 2 allowed value types

### 3.2 `tests/architecture/test_messages.py`

30 Tests:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestMessagesStructure` | 4 | Grundlegende Struktur |
| `TestContextContract` | 3 | Context Contract Validierung |
| `TestMessageIds` | 4 | Stabile Message-IDs |
| `TestStateMessages` | 3 | State Message Validierung |
| `TestTransitionMessages` | 4 | Transition Message Validierung |
| `TestCrossRefTopology` | 3 | Cross-Ref: Messages → Topology |
| `TestConformanceCommandPolicy` | 2 | Cross-Ref: Messages ↔ Command-Policy |
| `TestPresentationOnlyLayer` | 3 | Presentation-only Absicherung |
| `TestMessageNegative` | 4 | Negative Tests |

## 4. Testergebnisse

```
tests/architecture/test_messages.py ... 30 passed
tests/architecture/test_command_policy.py ... 42 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 173 passed
```

## 5. Nächste Schritte

1. **Phase 6**: Phase 6 in echte Substates zerlegen
2. **Phase 7**: Runtime-Executor bereinigen
3. **Phase 8**: Spec-Validator und Conformance-Checks

---

**Nächster Schritt:** Phase 6 in echte Substates zerlegen.
