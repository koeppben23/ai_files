"""Model Identity Resolver - Infrastructure layer.

Resolves model identity from environment variables.
This belongs in infrastructure layer because it accesses the host environment.
"""

from __future__ import annotations

import os

from governance.domain.model_identity import ModelIdentity, infer_context_limit


def resolve_from_environment() -> ModelIdentity | None:
    """Resolve model identity from environment variables.
    
    Environment variables (all optional, but provider+model_id required for trust):
    - OPENCODE_MODEL_PROVIDER: Model provider (e.g., 'anthropic', 'openai')
    - OPENCODE_MODEL_ID: Model identifier (e.g., 'claude-3-opus-20240229')
    - OPENCODE_MODEL_CONTEXT_LIMIT: Context limit in tokens (optional, will infer if missing)
    
    Returns:
        ModelIdentity with source="environment" if provider and model_id are set,
        None otherwise.
    """
    provider = os.environ.get("OPENCODE_MODEL_PROVIDER")
    model_id = os.environ.get("OPENCODE_MODEL_ID")
    context_limit_str = os.environ.get("OPENCODE_MODEL_CONTEXT_LIMIT")
    
    if not provider or not model_id:
        return None
    
    context_limit = 0
    if context_limit_str:
        try:
            context_limit = int(context_limit_str)
        except ValueError:
            pass
    
    if context_limit <= 0:
        context_limit = infer_context_limit(model_id)
    
    return ModelIdentity(
        provider=provider,
        model_id=model_id,
        context_limit=context_limit,
        source="environment",
    )
