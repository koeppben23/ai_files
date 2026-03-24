# Phase 4: Command-Policy separat modellieren (v3 - Deterministic /continue)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/command_policy.yaml`

---

## 1. Ziel

Extrahiere die Command-Policy aus der monolithischen `phase_api.yaml` in eine separate `command_policy.yaml`-Datei.

**Key Features:**
- Explicit Command→Event mapping (ADR-004)
- Deterministic /continue (exactly one guard per state)
- No constraints/textual semantics in runtime model
- Stable output policy IDs
- Terminal/Blocked state command restrictions

## 2. Prinzipien

### 2.1 /continue Determinism Contract

```yaml
- id: "cmd_continue"
  command: "/continue"
  behavior:
    type: "advance_routing"
    determinism: "exactly_one_guard_per_state"  # REQUIRED
  produces_events: "*_via_guards"  # Special: guard-determined
```

**Contract:**
- For each state, exactly one guard condition evaluates to true
- The matching transition produces exactly one event
- No fallback, no ambiguity, no silent mutations

### 2.2 No Constraints in Runtime Model

**FORBIDDEN fields in commands:**
- `constraints` - Removed entirely
- All behavioral rules must be in guards, not text

**Allowed fields:**
- Runtime: `id`, `command`, `allowed_in`, `mutating`, `behavior`, `produces_events`
- Non-runtime: `description` only

### 2.3 Universal Read-Only Commands

`/review` is universally allowed with explicit justification:
1. Pure read-only - never mutates governance state
2. Only produces local findings/verdict, no state events
3. Safe during blocking, rework, or critical situations
4. Users need review capability even when workflow is paused

### 2.4 Command Restriction Rules

```yaml
command_restrictions:
  - state_pattern: "*.terminal"
    blocked_command_types: ["persist_evidence", "start_implementation", ...]
    reason: "Terminal states are immutable"
```

### 2.5 Command Semantics

| Command | decision_scope | Purpose |
|---------|----------------|---------|
| `/review-decision` | workflow | Decides workflow/plan approval |
| `/implementation-decision` | workflow | Alias for /review-decision |

## 3. Erstellte Dateien

### 3.1 `governance_spec/command_policy.yaml`

**Commands (7):**
| Command | Mutating | Events | Determinism |
|---------|----------|--------|-------------|
| `/continue` | Yes | `*_via_guards` | exactly_one_guard_per_state |
| `/review` | No | (none) | read-only |
| `/ticket` | Yes | (via evidence) | - |
| `/plan` | Yes | (via evidence) | - |
| `/implement` | Yes | 2 events | - |
| `/review-decision` | Yes | 3 events | decision_scope: workflow |
| `/implementation-decision` | Yes | 3 events | alias: cmd_review_decision |

### 3.2 `tests/architecture/test_command_policy.py`

39 Tests:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestCommandPolicyStructure` | 3 | Grundlegende Struktur |
| `TestCommands` | 8 | Command Definitionen |
| `TestCommandNoConstraints` | 2 | Keine constraints Felder |
| `TestContinueDeterminism` | 3 | /continue determinism contract |
| `TestReviewUniversalJustification` | 3 | /review universal access |
| `TestCommandEventMapping` | 4 | Command→Event Mapping |
| `TestOutputPolicies` | 5 | Output Policy Validierung |
| `TestPhaseOutputPolicyMap` | 4 | Phase Mapping Integrität |
| `TestCommandRestrictions` | 4 | Terminal/Blocked rules |
| `TestCommandTopologyConsistency` | 3 | Cross-Spec Konsistenz |

## 4. Testergebnisse

```
tests/architecture/test_command_policy.py ... 39 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 140 passed
```

## 5. Nächste Schritte

1. **Phase 5**: Presentation/Messages herauslösen
2. **Phase 6**: Phase 6 in echte Substates zerlegen

---

**Nächster Schritt:** Presentation/Messages herauslösen.
