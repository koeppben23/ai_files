"""Model Identity Resolver - Infrastructure layer.

Resolves model identity from environment variables.
This belongs in infrastructure layer because it accesses the host environment.

TRUST MODEL:
- source="binding_env": Environment comes from installer-owned binding file (TRUSTED)
- source="process_env": Environment comes from user process (ADVISORY ONLY)

The distinction is critical: process environment can be user-controlled and
should NOT be trusted for audit. Only binding-owned environment is trusted.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from governance.domain.model_identity import ModelIdentity, infer_context_limit, ModelIdentitySource


def resolve_from_environment() -> ModelIdentity | None:
    """Resolve model identity from environment variables.
    
    Environment variables:
    - OPENCODE_MODEL_PROVIDER: Model provider (e.g., 'anthropic', 'openai')
    - OPENCODE_MODEL_ID: Model identifier (e.g., 'claude-3-opus-20240229')
    - OPENCODE_MODEL_CONTEXT_LIMIT: Context limit in tokens (optional, will infer if missing)
    - OPENCODE_BINDING_FILE: Path to binding file (determines trust)
    
    Trust Determination:
    - If OPENCODE_BINDING_FILE exists and is valid → source="binding_env" (TRUSTED)
    - Otherwise → source="process_env" (ADVISORY ONLY)
    
    Context Limit Resolution:
    - If OPENCODE_MODEL_CONTEXT_LIMIT is explicitly set → use as-is (even if negative)
    - If not set or invalid → try inference (deprecated, advisory only)
    - Explicit values are preserved so caller can validate
    
    Returns:
        ModelIdentity with appropriate source, None if provider/model_id missing.
    """
    provider = os.environ.get("OPENCODE_MODEL_PROVIDER")
    model_id = os.environ.get("OPENCODE_MODEL_ID")
    context_limit_str = os.environ.get("OPENCODE_MODEL_CONTEXT_LIMIT")
    
    if not provider or not model_id:
        return None
    
    source = _determine_source()
    
    explicit_context_limit = False
    context_limit = 0
    
    if context_limit_str:
        try:
            context_limit = int(context_limit_str)
            explicit_context_limit = True
        except ValueError:
            pass
    
    if not explicit_context_limit:
        context_limit = infer_context_limit(model_id)
    
    return ModelIdentity(
        provider=provider,
        model_id=model_id,
        context_limit=context_limit,
        source=source,
    )


def _determine_source() -> ModelIdentitySource:
    """Determine the source of model identity.
    
    Check if environment comes from a binding file (trusted) or
    from user process environment (advisory only).
    """
    binding_file = os.environ.get("OPENCODE_BINDING_FILE", "")
    
    if binding_file and Path(binding_file).exists():
        return "binding_env"
    
    return "process_env"
