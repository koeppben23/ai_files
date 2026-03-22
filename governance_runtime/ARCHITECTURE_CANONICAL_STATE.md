# Architecture: Canonical State Model

**Status:** Implemented (Sprint E)  
**Branch:** `refactor/governance-layer-separation`

## Overview

Sprint E introduces a canonical state model to centralize legacy field name resolution and establish a single source of truth for session state field access.

## Problem

The codebase historically supported multiple field name conventions:
- PascalCase: `Phase`, `Next`, `Status`
- snake_case: `phase`, `next`, `status`
- Mixed: `Phase5State`, `phase5_completed`

This led to:
- Scattered alias resolution logic (`.get("Phase") or .get("phase")` chains in ~50 files)
- Inconsistent field access patterns
- Maintenance burden when adding new fields

## Solution

### Canonical Model

```python
# governance_runtime/application/dto/canonical_state.py
CanonicalSessionState = TypedDict('CanonicalSessionState', {
    'phase': str,
    'next_action': str,
    'active_gate': str,
    'status': str,
    # ... all fields use snake_case
})
```

### Centralized Resolution

```python
# governance_runtime/application/services/state_normalizer.py
def normalize_to_canonical(state: dict) -> CanonicalSessionState:
    """Convert legacy state dict to canonical form."""
    # All alias resolution happens here
```

### Alias Mappings

```python
# governance_runtime/application/dto/field_aliases.py
FIELD_ALIASES = {
    "phase": ["Phase"],           # canonical -> legacy aliases
    "next_action": ["Next", "next"],
    "workflow_complete": ["WorkflowComplete"],
    # ...
}
```

## Architecture Rules

1. **Single Resolution Point:** Alias resolution only in `state_normalizer.py`
2. **Kernel Uses Canonical:** Kernel code must use `CanonicalSessionState` via `normalize_to_canonical()`
3. **Legacy Writes OK:** Entrypoints may write legacy field names for backward compatibility
4. **Architecture Test:** `test_alias_resolution_only_in_allowed_modules` enforces the rule

## Migration Status

### Completed (Sprint E)

| Module | Status |
|--------|--------|
| `state_normalizer.py` | Canonical source of truth |
| `phase5_normalizer.py` | Uses `normalize_to_canonical()` |
| `orchestrator.py` | Uses canonical state helpers |
| `state_accessor.py` | Delegates to normalizer |
| `session_reader.py` | Critical paths migrated |

### Remaining Legacy

| Module | Status |
|--------|--------|
| `legacy_compat.py` | Intentionally in allowlist |
| `policy_resolver.py` | Planned for Phase 3 |
| Entrypoints | Gradual migration |

## Usage

```python
from governance_runtime.application.services.state_normalizer import normalize_to_canonical

# Read state canonically
canonical = normalize_to_canonical(raw_state)
phase = canonical["phase"]  # guaranteed canonical name

# Use helpers for common access patterns
from governance_runtime.application.services.state_accessor import get_phase, get_active_gate
phase = get_phase(state)
```

## Testing

- Unit tests: `tests/unit/test_state_normalizer.py`, `tests/unit/test_state_accessor.py`
- Architecture tests: `tests/architecture/test_import_rules.py`
- All 61 tests pass

## Commits

```
d5acc58 feat(sprint-e): migrate session_reader to use canonical state helpers (Phase 4)
c2854f3 fix(sprint-e): remove dead phase6_max_iterations fallback
630a0db feat(sprint-e): migrate state_accessor to use normalize_to_canonical() (Phase 3)
12896a4 feat(sprint-e): migrate phase5_normalizer to use normalize_to_canonical() (Phase 2)
f77b043 feat(sprint-e): integrate StateNormalizer in session_reader and orchestrator
0c7c55a feat(sprint-e): complete Phase 2 - StateNormalizer with architecture guard
0a98faa feat(sprint-e): add StateNormalizer (Phase 2)
ba47dc3 fix(sprint-e): rename next_step to next_action in canonical model
ac04c93 feat(sprint-e): define canonical state model (Phase 1)
```

## Future Work

1. **Integration Tests:** Add E2E tests for canonical state path
2. **Further Migration:** Complete `policy_resolver.py` migration
3. **Performance:** Consider caching for repeated `normalize_to_canonical()` calls (measure first)
