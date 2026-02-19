# Model Identity Resolution Strategy

## Problem

Hardcoded model context limits become stale immediately. New models are released
frequently, and the registry can never be complete.

From a governance perspective, hardcoded `KNOWN_CONTEXT_LIMITS` is problematic:
- **Unauditable**: Incompleteness cannot be detected
- **Bypasses Policy Layer**: Changes happen via code changes, not policy activation

## Trust Sources for Context Limits

### 1. Provider Metadata API (Ideal - When Available)

Some providers offer official APIs to query model metadata:

**Gemini Example:**
```python
from google.generativeai import GenerativeModel
model = genai.get_model("gemini-1.5-pro")
# Returns: input_token_limit, output_token_limit, etc.
```

This is the ideal state:
- Kernel queries provider metadata → writes as Evidence → uses deterministically
- No hardcoding, fully auditable

**Limitations:**
- Not standardized across providers
- OpenAI/Anthropic don't guarantee metadata API endpoints
- Local providers (Ollama) may not have metadata APIs

### 2. Trusted Configuration (Required When No Provider API)

When provider metadata is unavailable, context limits MUST come from a trusted layer:

**Environment Variables (from activation pack/host config):**
```bash
export OPENCODE_MODEL_PROVIDER=anthropic
export OPENCODE_MODEL_ID=claude-3-5-sonnet-20241022
export OPENCODE_MODEL_CONTEXT_LIMIT=200000
```

**This is the SSOT approach:**
- Environment comes from activation pack or pack-lock
- Changes go through policy activation, not code changes
- Audit trail captures when/why limits changed

### 3. Versioned Policy Artifact (For Registries)

If a registry is needed (many providers), it MUST be:
- A versioned file (not code constant)
- Signed/hashed (activation pack / pack-lock)
- Audit events when used/updated
- Fail-closed if incomplete or contradictory

**NOT acceptable:**
```python
# ❌ WRONG - Code constant, bypasses policy
KNOWN_CONTEXT_LIMITS = {"gpt-4": 8192, ...}
```

**Acceptable:**
```yaml
# ✅ CORRECT - Versioned policy artifact
# context_limits.yaml (in activation pack)
models:
  - provider: anthropic
    model_id: claude-3-5-sonnet-*
    context_limit: 200000
    effective_date: 2024-10-01
    source: documentation
```

## Implementation

### Domain Layer: ModelIdentity with Source

```python
@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model_id: str
    context_limit: int
    source: Literal["environment", "llm_context", "user_input", "inferred", "unresolved"]
    
    def is_trusted_for_audit(self) -> bool:
        """Only environment source is trusted."""
        return self.source == "environment"
```

### Infrastructure Layer: Environment Resolver

```python
# governance/infrastructure/model_identity_resolver.py
def resolve_from_environment() -> ModelIdentity | None:
    """Resolve from trusted environment variables."""
    provider = os.environ.get("OPENCODE_MODEL_PROVIDER")
    model_id = os.environ.get("OPENCODE_MODEL_ID")
    context_limit = os.environ.get("OPENCODE_MODEL_CONTEXT_LIMIT")
    
    if not provider or not model_id:
        return None
    
    return ModelIdentity(
        provider=provider,
        model_id=model_id,
        context_limit=int(context_limit or 0),
        source="environment",
    )
```

## Fail-Closed Behavior

When context limit is unknown:

### Option A: Explicit Limit Required (Recommended for Governance)
- Kernel REQUIRES context_limit from trusted source
- Missing → `BLOCKED` with reason `MODEL_CONTEXT_LIMIT_REQUIRED`
- No silent fallbacks

### Option B: Safe Cap (Only with Explicit Policy)
- Set conservative limit (e.g., 32k) with explicit policy documentation
- Trigger early compaction/pruning
- Audit event logged
- NOT silent behavior

### Option C: Runtime Error as Evidence
- Capture `context_length_exceeded` errors
- Extract limit from error message (if available)
- Write as Evidence for future runs

## Trust Categories

| Category | Description | Can Affect |
|----------|-------------|------------|
| `trusted_for_audit` | May be used as truth in audit records | Audit, Routing, Enforcement |
| `trusted_for_routing` | May influence kernel routing decisions | Routing, Enforcement |
| `advisory_only` | Hints only, must not affect enforcement | None |
| `blocks_audit` | Cannot proceed with audit | None - must be resolved |

## Source Trust Levels

| Source | Trust Level | Description |
|--------|-------------|-------------|
| `binding_env` | `trusted_for_audit` | From installer-owned canonical root / pack-lock |
| `host_capability` | `trusted_for_routing` | From host capability assertion |
| `provider_metadata` | `advisory_only` | From provider API (requires verification) |
| `process_env` | `advisory_only` | From user process environment (user-controlled) |
| `llm_context` | `advisory_only` | Self-reported by LLM (hallucination risk) |
| `user_input` | `advisory_only` | User-provided (unverified) |
| `inferred` | `advisory_only` | Guessed from model_id patterns (stale risk) |
| `unresolved` | `blocks_audit` | Could not determine identity |

## Critical Distinction: binding_env vs process_env

**`binding_env`** (TRUSTED FOR AUDIT):
- Environment comes from installer-owned binding file
- `OPENCODE_BINDING_FILE` points to a valid `governance.paths.json`
- Changes go through policy activation, not ad-hoc env var changes
- This is the **only** source trusted for audit evidence

**`process_env`** (ADVISORY ONLY):
- Environment comes from user process environment
- Could be user-controlled (`export OPENCODE_MODEL_ID=...`)
- NOT trusted for audit because anyone can set environment variables
- Only advisory - must not affect enforcement decisions

### Example: How Trust is Determined

```python
# In model_identity_resolver.py
def _determine_source() -> ModelIdentitySource:
    binding_file = os.environ.get("OPENCODE_BINDING_FILE", "")
    
    if binding_file and Path(binding_file).exists():
        return "binding_env"  # TRUSTED
    
    return "process_env"  # ADVISORY ONLY
```

## Reason Codes

When model identity issues block execution, these reason codes are used:

| Code | Summary |
|------|---------|
| `BLOCKED-MODEL-IDENTITY-UNTRUSTED` | Model identity not from trusted source |
| `BLOCKED-MODEL-CONTEXT-LIMIT-REQUIRED` | Context limit required but not provided |
| `BLOCKED-MODEL-CONTEXT-LIMIT-UNKNOWN` | Context limit could not be determined |
| `BLOCKED-MODEL-METADATA-FETCH-FAILED` | Provider metadata API fetch failed |
| `BLOCKED-MODEL-IDENTITY-SOURCE-INVALID` | Invalid source value |

## Deprecated: KNOWN_CONTEXT_LIMITS

The `KNOWN_CONTEXT_LIMITS` dictionary in code is deprecated because:

1. **Stale Immediately**: New models released before code updates
2. **No Policy Trail**: Changes via code PR, not policy activation
3. **Unauditable**: No way to detect incompleteness
4. **Not SSOT**: Aggregators (models.dev) can be wrong

**Migration Path:**
1. Set `OPENCODE_MODEL_CONTEXT_LIMIT` in activation pack
2. Remove reliance on `infer_context_limit()`
3. Treat missing context_limit as `BLOCKED`

## Audit Implications

| Source | Trusted for Audit | Reason |
|--------|-------------------|--------|
| `environment` | ✅ YES | From activation pack/host config |
| `llm_context` | ❌ NO | LLM could hallucinate its identity |
| `user_input` | ❌ NO | Unverified input |
| `inferred` | ❌ NO | Based on stale patterns |
| `unresolved` | ❌ NO | Blocks audit |

Evidence bundle MUST include `source` field. Verification flags non-environment sources as incomplete.

## Practical Guidance

1. **Provider offers metadata API** → Use it (Gemini example)
2. **No provider API** → Require explicit limit in activation pack
3. **Using a registry** → Make it a versioned policy artifact
4. **Missing limit** → Block, don't silently guess

**OpenCode/Models.dev**: Good for UX, NOT governance SSOT.
