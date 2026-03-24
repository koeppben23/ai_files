# Governance Configuration

**Status:** Implemented  
**Feature Branch:** `feat/governance-config-installer-materialize`

## Overview

`governance-config.json` is the policy configuration file for the AI Engineering Governance Platform. It allows operators to customize governance behavior at the workspace level without code changes.

## Location

```
~/.config/opencode/workspaces/<repo-fingerprint>/governance-config.json
```

## Bootstrap Materialization

During workspace bootstrap, `governance-config.json` is automatically materialized to the workspace directory if not already present. This ensures every workspace has sensible defaults out-of-the-box.

**Idempotent:** Existing configurations are never overwritten. Custom configurations take precedence.

**Graceful degradation:** If the default asset cannot be read (e.g., packaging issues), bootstrap continues without error and falls back to hardcoded defaults.

## Schema

**File:** `governance_runtime/assets/schemas/governance-config.v1.schema.json`

**Note:** `$schema` is optional. The default asset intentionally omits it to avoid resolution issues at the fp-scoped path.

```json
{
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

workspace_dir = Path("~/.config/opencode/workspaces/<fingerprint>")
config = load_governance_config(workspace_dir)
# Or pass None to get defaults:
config = load_governance_config(None)
```

### Getting Review Iterations

```python
from governance_runtime.infrastructure.governance_config_loader import get_review_iterations

workspace_dir = Path("~/.config/opencode/workspaces/<fingerprint>")
phase5_max, phase6_max = get_review_iterations(workspace_dir)
# Returns (3, 3) by default
```

### Phase5 Usage

The Phase 5 self-review loop uses governance config:

```python
from governance_runtime.entrypoints.phase5_plan_record_persist import _get_phase5_max_review_iterations

workspace_dir = Path("~/.config/opencode/workspaces/<fingerprint>")
max_iterations = _get_phase5_max_review_iterations(workspace_dir)
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
2. **Bootstrap Materialization:** Config is automatically materialized during workspace bootstrap (idempotent)
3. **Fail-Closed:** Invalid config raises errors rather than silently falling back
4. **Workspace-Scoped:** Each workspace can have its own configuration (via fingerprint)
5. **State Override:** Runtime state values always take precedence over config defaults
6. **Central Resolver:** `workspace_resolver.py` provides single source of truth for workspace path resolution
7. **Package Resources:** Asset loading uses `importlib.resources` for robust resolution

## Implementation Status

- **V1 Complete:** Review iteration configuration for Phase 5 and Phase 6
- **Bootstrap Materialization:** Config automatically materialized during workspace bootstrap
- **Central Workspace Resolver:** `workspace_resolver.py` consolidates fingerprint/config-path resolution
- **Loader Cache:** No workspace-keyed cache in V1; correctness over optimization

## Related Files

- Default Asset: `governance_runtime/assets/config/governance-config.json`
- Schema: `governance_runtime/assets/schemas/governance-config.v1.schema.json`
- Defaults: `governance_runtime/domain/default_governance_config.py`
- Loader: `governance_runtime/infrastructure/governance_config_loader.py`
- Workspace Resolver: `governance_runtime/infrastructure/workspace_resolver.py`
- Bootstrap Materialization: `governance_runtime/application/use_cases/bootstrap_persistence.py`
- Phase5 wiring: `governance_runtime/entrypoints/phase5_plan_record_persist.py`
- Phase6 wiring: `governance_runtime/kernel/phase_kernel.py`
- Session reader: `governance_runtime/entrypoints/session_reader.py`

## Future Considerations

- Workspace-keyed loader cache for performance
- CLI override for V2
- Multi-workspace integration tests
