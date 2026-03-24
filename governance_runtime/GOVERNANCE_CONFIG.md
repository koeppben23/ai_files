# Governance Configuration

**Status:** Implemented  
**Feature Branch:** `feat/governance-config-json`

## Overview

`governance-config.json` is the policy configuration file for the AI Engineering Governance Platform. It allows operators to customize governance behavior at the workspace level without code changes.

## Location

```
<workspace-root>/governance-config.json
```

Where `<workspace-root>` is typically:
```
~/.config/opencode/workspaces/<repo-fingerprint>/
```

## Schema

**File:** `governance_runtime/assets/schemas/governance-config.v1.schema.json`

```json
{
  "$schema": "governance-config.v1.schema.json",
  "review": {
    "phase5_max_review_iterations": 3,
    "phase6_max_review_iterations": 3
  },
  "pipeline": {
    "allow_pipeline_mode": true,
    "auto_approve_enabled": true
  },
  "regulated": {
    "allow_auto_approve": false,
    "require_governance_mode_active": true
  }
}
```

## Configuration Sections

### `review`

Controls review loop iteration limits.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `phase5_max_review_iterations` | integer | 3 | Maximum self-review iterations for Phase 5 (Plan Architecture Review) |
| `phase6_max_review_iterations` | integer | 3 | Maximum self-review iterations for Phase 6 (Implementation Review) |

**Bounds:** 1 - 100

### `pipeline`

Controls pipeline mode behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allow_pipeline_mode` | boolean | true | Whether pipeline mode is allowed |
| `auto_approve_enabled` | boolean | true | Whether auto-approve is enabled in pipeline mode |

### `regulated`

Controls regulated mode behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allow_auto_approve` | boolean | false | Whether auto-approve is allowed in regulated mode (should remain false) |
| `require_governance_mode_active` | boolean | true | Whether governance-mode.json must be active for regulated enforcement |

## Behavior Rules

| Scenario | Behavior |
|----------|----------|
| File missing | Return defaults (backward compatible) |
| File present + valid | Use loaded values |
| File present + invalid | Fail-closed (RuntimeError) |
| Unknown keys | Rejected (validation error) |
| State value present | Takes precedence over config |

## Usage

### Loading Configuration

```python
from governance_runtime.infrastructure.governance_config_loader import load_governance_config

config = load_governance_config(workspace_root)
```

### Getting Review Iterations

```python
from governance_runtime.infrastructure.governance_config_loader import get_review_iterations

phase5_max, phase6_max = get_review_iterations(workspace_root)
# Returns (3, 3) by default
```

### Phase5 Usage

The Phase 5 self-review loop uses governance config:

```python
from governance_runtime.entrypoints.phase5_plan_record_persist import _get_phase5_max_review_iterations

max_iterations = _get_phase5_max_review_iterations(workspace_root)
```

### Phase6 Usage

The Phase 6 implementation review loop uses governance config:

```python
from governance_runtime.kernel.phase_kernel import _phase6_max_review_iterations

state = {"repo_fingerprint": "abc123", ...}
max_iterations = _phase6_max_review_iterations(state)
# Falls back to governance config if not in state
```

## Validation

Configuration is validated against the JSON schema on load. Invalid configurations raise `RuntimeError`.

```python
from governance_runtime.infrastructure.governance_config_loader import validate_governance_config

errors = validate_governance_config(config)
if errors:
    raise RuntimeError(f"Config validation failed: {errors}")
```

## Architecture Notes

1. **Configuration Loader:** `governance_config_loader.py` provides the main API (`load_governance_config`, `get_review_iterations`)
2. **Fail-Closed:** Invalid config raises errors rather than silently falling back
3. **Workspace-Scoped:** Each workspace can have its own configuration (via fingerprint)
4. **State Override:** Runtime state values always take precedence over config defaults
5. **Schema Validation:** Currently uses manual validation; JSON schema file serves as formal contract

## Implementation Status

- **V1 Complete:** Review iteration configuration for Phase 5 and Phase 6
- **Workspace Resolution:** Distributed across call sites (session_reader, phase_kernel, phase5_plan_record_persist)
- **Loader Cache:** No workspace-keyed cache in V1; correctness over optimization

## Related Files

- Schema: `governance_runtime/assets/schemas/governance-config.v1.schema.json`
- Defaults: `governance_runtime/domain/default_governance_config.py`
- Loader: `governance_runtime/infrastructure/governance_config_loader.py`
- Phase5 wiring: `governance_runtime/entrypoints/phase5_plan_record_persist.py`
- Phase6 wiring: `governance_runtime/kernel/phase_kernel.py`
- Session reader: `governance_runtime/entrypoints/session_reader.py`

## Future Considerations

- Central workspace resolution helper (consolidate fingerprint/config-path resolution)
- Workspace-keyed loader cache for performance
- CLI override for V2
- Multi-workspace integration tests
