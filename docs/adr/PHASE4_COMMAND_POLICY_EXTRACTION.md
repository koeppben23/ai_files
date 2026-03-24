# Phase 4: Command-Policy separat modellieren (v4 - Target architecture)

**Status:** Completed  
**Date:** 2026-03-24  
**Source:** `governance_spec/command_policy.yaml`

---

## 1. Ziel

Extrahiere die Command-Policy aus der monolithischen `phase_api.yaml` in eine separate `command_policy.yaml`-Datei.

**This is now the TARGET architecture policy, not transitional:**
- Phase 6 commands target substates (6.approved, 6.presentation)
- *_via_guards is formally hardened (only /continue)
- No constraints or textual semantics

## 2. Prinzipien

### 2.1 Phase 6 Target Architecture (per ADR-003)

```yaml
/implement → allowed_in: ["6.approved"]
/review-decision → allowed_in: ["6.presentation"]
/implementation-decision → allowed_in: ["6.presentation"]
```

These states don't exist in topology yet (Phase 6 zerlegung pending).
Tests handle this by recognizing future states from ADR-003.

### 2.2 *_via_guards Contract

```yaml
produces_events: "*_via_guards"  # SPECIAL: only /continue may use this
```

**Contract:**
- Only `/continue` may use `*_via_guards`
- Other commands must have explicit event list `[]` or `["event1", ...]`
- Tests enforce this strictly

### 2.3 alias_of (not aliases)

```yaml
behavior:
  alias_of: "cmd_review_decision"  # Single alias reference
```

### 2.4 Command Restrictions with Documented Semantics

```yaml
command_restrictions:
  - state_pattern: "*.terminal"
    # NOTE: This matches states where terminal=true in topology,
    # not by name convention. Runtime resolves against terminal flag.
    blocked_command_types: [...]
    reason: "Terminal states have terminal=true in topology, are immutable"
```

## 3. Erstellte Dateien

### 3.1 `governance_spec/command_policy.yaml`

**Commands (7):**
| Command | Target State | Mutating | Events |
|---------|--------------|----------|--------|
| `/continue` | * | Yes | `*_via_guards` |
| `/review` | * | No | `[]` |
| `/ticket` | 4 | Yes | `[]` |
| `/plan` | 4, 5 | Yes | `[]` |
| `/implement` | **6.approved** | Yes | 2 events |
| `/review-decision` | **6.presentation** | Yes | 3 events |
| `/implementation-decision` | **6.presentation** | Yes | 3 events (alias) |

### 3.2 `tests/architecture/test_command_policy.py`

42 Tests:

| Testklasse | Tests | Beschreibung |
|------------|-------|--------------|
| `TestCommandPolicyStructure` | 3 | Grundlegende Struktur |
| `TestCommands` | 8 | Command Definitionen |
| `TestCommandNoConstraints` | 2 | Keine constraints Felder |
| `TestContinueDeterminism` | 3 | /continue determinism contract |
| `TestReviewUniversalJustification` | 3 | /review universal access |
| `TestCommandEventMapping` | 4 | Command→Event Mapping |
| `TestViaGuardsContract` | 3 | *_via_guards nur für /continue |
| `TestOutputPolicies` | 5 | Output Policy Validierung |
| `TestPhaseOutputPolicyMap` | 4 | Phase Mapping Integrität |
| `TestCommandRestrictions` | 4 | Terminal/Blocked rules |
| `TestCommandTopologyConsistency` | 3 | Cross-Spec Konsistenz |

## 4. Testergebnisse

```
tests/architecture/test_command_policy.py ... 42 passed
tests/architecture/test_guards.py ... 33 passed
tests/architecture/test_topology.py ... 34 passed
tests/architecture/test_spec_inventory.py ... 18 passed
Total: 143 passed
```

## 5. Nächste Schritte

1. **Phase 5**: Presentation/Messages herauslösen
2. **Phase 6**: Phase 6 in echte Substates zerlegen (6.approved, 6.presentation, etc.)

---

**Nächster Schritt:** Presentation/Messages herauslösen.
