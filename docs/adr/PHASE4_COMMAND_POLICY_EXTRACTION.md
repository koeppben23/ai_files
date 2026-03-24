# Phase 4: Command-Policy separat modellieren (v2 - Strict with event mapping)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/command_policy.yaml`

---

## 1. Ziel

Extrahiere die Command-Policy aus der monolithischen `phase_api.yaml` in eine separate `command_policy.yaml`-Datei.

**Key Features:**
- Explicit Command→Event mapping (ADR-004)
- Stable IDs for output policy references (not index-based)
- Phase 6 commands marked as transitional
- Closed schema with strict field validation

## 2. Prinzipien

### 2.1 Command→Event Mapping (ADR-004)

```yaml
command:
  id: string
  command: string
  allowed_in: "*" | string[]
  mutating: boolean
  behavior:
    type: string
  produces_events: string[]  # Events this command produces
```

**Semantics:**
- Commands are user/system inputs
- Events are machine-internal signals for state transitions
- Each command explicitly lists the events it produces
- Empty `produces_events` means state change via evidence, not direct event

### 2.2 Stable Output Policy References

```yaml
output_policies:
  - id: "op.phase5.review_only"  # Stable ID (not index)
    state_id: "5"
    ...

phase_output_policy_map:
  - state_id: "5"
    output_policy_ref: "op.phase5.review_only"  # Stable reference
```

**Rules:**
- Each output policy has a stable ID starting with `op.`
- References use stable IDs, not indices like `output_policies[0]`
- No orphaned policies (all policies must be mapped)
- No duplicate state mappings

### 2.3 Transitional Phase 6 Commands

Commands targeting State "6" (Phase 6 monolith) are marked as **TRANSITIONAL**:

```yaml
- id: "cmd_implement"
  command: "/implement"
  allowed_in:
    - "6"  # TRANSITIONAL: per ADR-003 should be 6.approved
```

**After Phase 6 zerlegung:**
- `/implement` → `6.approved`
- `/review-decision` → `6.presentation`

### 2.4 Closed Schema

Runtime fields for command objects:
```python
RUNTIME_COMMAND_FIELDS = {
    "id", "command", "allowed_in", "mutating", "behavior", "produces_events"
}
NON_RUNTIME_COMMAND_FIELDS = {"description", "constraints"}
```

Unknown fields are rejected by tests.

## 3. Erstellte Dateien

### 3.1 `governance_spec/command_policy.yaml`

**Commands (7):**
| Command | Type | Mutating | Events Produced |
|---------|------|----------|-----------------|
| `/continue` | advance_routing | Yes | (determined by guards) |
| `/review` | review_readonly | No | (read-only, no events) |
| `/ticket` | persist_evidence | Yes | (via evidence) |
| `/plan` | persist_evidence | Yes | (via evidence) |
| `/implement` | start_implementation | Yes | implementation_started, implementation_execution_in_progress |
| `/review-decision` | submit_review_decision | Yes | workflow_approved, review_changes_requested, review_rejected |
| `/implementation-decision` | submit_review_decision | Yes | workflow_approved, review_changes_requested, review_rejected |

**Output Policies (1):**
- `op.phase5.review_only`: Phase 5 planning only, no implementation

### 3.2 `tests/architecture/test_command_policy.py`

35 Tests für die strikte Command-Policy-Validierung:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestCommandPolicyStructure` | 3 | Grundlegende Struktur |
| `TestCommands` | 10 | Command Definitionen |
| `TestCommandEventMapping` | 3 | Command→Event Mapping |
| `TestCommandNoUnknownFields` | 2 | Strikte Feldvalidierung |
| `TestOutputPolicies` | 9 | Output Policy Validierung |
| `TestPhaseOutputPolicyMap` | 6 | Phase Mapping Integrität |
| `TestCommandTopologyConsistency` | 4 | Cross-Spec Konsistenz |

## 4. Testergebnisse

```
tests/architecture/test_command_policy.py ... 35 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 136 passed
```

## 5. Nächste Schritte

1. **Phase 5**: Presentation/Messages herauslösen
2. **Phase 6**: Phase 6 in echte Substates zerlegen

---

**Nächster Schritt:** Presentation/Messages herauslösen.
