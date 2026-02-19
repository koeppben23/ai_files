"""Model Identity - Evidence for reproducibility.

Model identity is critical for reproducibility and audit.
Every run MUST record which model produced the output.

IMPORTANT: Model identity source determines trustworthiness for audit.

TRUST CATEGORIES:
- trusted_for_audit: May be used as truth in audit records
- trusted_for_routing: May influence kernel routing decisions
- advisory_only: Hints only, must not affect enforcement

SOURCE TRUST LEVELS:
- "binding_env": TRUSTED FOR AUDIT - from installer-owned/pack-lock/activation
- "host_capability": TRUSTED FOR ROUTING - from host capability assertion
- "provider_metadata": ADVISORY ONLY - from provider API (requires verification)
- "process_env": ADVISORY ONLY - from user process environment (user-controlled)
- "llm_context": ADVISORY ONLY - self-reported by LLM (hallucination risk)
- "user_input": ADVISORY ONLY - user-provided (unverified)
- "inferred": ADVISORY ONLY - guessed from model_id patterns (stale risk)
- "unresolved": BLOCKS AUDIT - could not determine identity
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

ModelIdentitySource = Literal[
    "binding_env",      # From installer-owned canonical root / pack-lock
    "host_capability",  # From host capability assertion
    "provider_metadata", # From provider API (unverified)
    "process_env",      # From user process environment (user-controlled)
    "llm_context",      # Self-reported by LLM
    "user_input",       # User-provided
    "inferred",         # Guessed from model_id patterns
    "unresolved",       # Could not determine
]


class TrustLevel(Enum):
    """Trust level for model identity sources."""
    TRUSTED_FOR_AUDIT = "trusted_for_audit"
    TRUSTED_FOR_ROUTING = "trusted_for_routing"
    ADVISORY_ONLY = "advisory_only"
    BLOCKS_AUDIT = "blocks_audit"


SOURCE_TRUST_LEVELS: dict[ModelIdentitySource, TrustLevel] = {
    "binding_env": TrustLevel.TRUSTED_FOR_AUDIT,
    "host_capability": TrustLevel.TRUSTED_FOR_ROUTING,
    "provider_metadata": TrustLevel.ADVISORY_ONLY,
    "process_env": TrustLevel.ADVISORY_ONLY,
    "llm_context": TrustLevel.ADVISORY_ONLY,
    "user_input": TrustLevel.ADVISORY_ONLY,
    "inferred": TrustLevel.ADVISORY_ONLY,
    "unresolved": TrustLevel.BLOCKS_AUDIT,
}


@dataclass(frozen=True)
class ModelIdentity:
    """Immutable model identity for evidence chain.
    
    This is CRITICAL for reproducibility. Different models may produce
    different outputs for the same input, so recording model identity
    is essential for audit and debugging.
    """
    
    provider: str
    """Model provider (e.g., 'anthropic', 'openai', 'google')"""
    
    model_id: str
    """Model identifier (e.g., 'claude-3-opus-20240229', 'gpt-4-turbo')"""
    
    context_limit: int
    """Maximum context length in tokens"""
    
    source: ModelIdentitySource = "unresolved"
    """Source of the identity - determines trustworthiness for audit.
    
    TRUSTED FOR AUDIT: "binding_env" (installer-owned/pack-lock)
    TRUSTED FOR ROUTING: "host_capability"
    ADVISORY ONLY: "provider_metadata", "process_env", "llm_context", "user_input", "inferred"
    BLOCKS AUDIT: "unresolved"
    """
    
    temperature: float = 0.0
    """Sampling temperature (0.0 = deterministic)"""
    
    version: str | None = None
    """Model version/snapshot if available"""
    
    quantization: str | None = None
    """Quantization level if applicable (e.g., '4bit', '8bit')"""
    
    deployment_id: str | None = None
    """Deployment/endpoint ID for enterprise models"""
    
    def trust_level(self) -> TrustLevel:
        """Get the trust level for this identity source."""
        return SOURCE_TRUST_LEVELS.get(self.source, TrustLevel.ADVISORY_ONLY)
    
    def is_trusted_for_audit(self) -> bool:
        """Check if this identity is trusted for audit evidence.
        
        Only binding_env (installer-owned/pack-lock) is trusted for audit.
        All other sources are advisory or blocking.
        """
        return self.trust_level() == TrustLevel.TRUSTED_FOR_AUDIT
    
    def is_trusted_for_routing(self) -> bool:
        """Check if this identity is trusted for routing decisions.
        
        binding_env and host_capability are trusted for routing.
        """
        level = self.trust_level()
        return level in (TrustLevel.TRUSTED_FOR_AUDIT, TrustLevel.TRUSTED_FOR_ROUTING)
    
    def trust_warning(self) -> str | None:
        """Return warning message if identity is not trusted for audit."""
        level = self.trust_level()
        
        if level == TrustLevel.TRUSTED_FOR_AUDIT:
            return None
        
        if level == TrustLevel.BLOCKS_AUDIT:
            return "Model identity unresolved - BLOCKS audit"
        
        warnings_map = {
            "host_capability": "Model identity from host capability - trusted for routing only, NOT audit",
            "provider_metadata": "Model identity from provider API - ADVISORY ONLY, not verified",
            "process_env": "Model identity from process environment - ADVISORY ONLY (user-controlled)",
            "llm_context": "Model identity self-reported by LLM - ADVISORY ONLY (hallucination risk)",
            "user_input": "Model identity from user input - ADVISORY ONLY (unverified)",
            "inferred": "Model identity inferred from model_id - ADVISORY ONLY (stale registry)",
        }
        return warnings_map.get(self.source, "Unknown model identity source")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "provider": self.provider,
            "model_id": self.model_id,
            "context_limit": self.context_limit,
            "source": self.source,
            "temperature": self.temperature,
        }
        if self.version is not None:
            result["version"] = self.version
        if self.quantization is not None:
            result["quantization"] = self.quantization
        if self.deployment_id is not None:
            result["deployment_id"] = self.deployment_id
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelIdentity:
        """Create from dictionary."""
        return cls(
            provider=data.get("provider", "unknown"),
            model_id=data.get("model_id", "unknown"),
            context_limit=data.get("context_limit", 0),
            source=data.get("source", "unresolved"),
            temperature=data.get("temperature", 0.0),
            version=data.get("version"),
            quantization=data.get("quantization"),
            deployment_id=data.get("deployment_id"),
        )
    
    def compute_hash(self) -> str:
        """Compute deterministic hash for this identity."""
        import hashlib
        import json
        
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# Known model context limits for validation
# DEPRECATION NOTICE: This dictionary will be removed in a future version.
# Use resolve_from_environment() with OPENCODE_MODEL_CONTEXT_LIMIT instead.
# Stale context limits cause audit failures. Environment variables are the
# authoritative source.
#
# Order matters: more specific patterns should come first
KNOWN_CONTEXT_LIMITS: dict[str, int] = {
    # Anthropic
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    
    # OpenAI - order matters, more specific first
    "gpt-4-turbo": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4o": 128000,
    "gpt-4-32k": 32768,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    
    # Google
    "gemini-1.5-pro": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-pro": 32760,
    
    # Local/Other
    "llama-2-70b": 4096,
    "llama-3-70b": 8192,
    "mistral-large": 32000,
    "codellama-34b": 16384,
}


def infer_context_limit(model_id: str) -> int:
    """Infer context limit from model ID.
    
    Uses known model registry. Returns 0 if unknown.
    Prioritizes more specific patterns (e.g., gpt-4-turbo before gpt-4).
    
    DEPRECATION WARNING: This function uses a hardcoded registry that
    becomes stale as models are updated. Prefer OPENCODE_MODEL_CONTEXT_LIMIT
    environment variable for trusted context limits.
    """
    warnings.warn(
        "infer_context_limit() uses a hardcoded registry that may be stale. "
        "Set OPENCODE_MODEL_CONTEXT_LIMIT environment variable for trusted context limits.",
        DeprecationWarning,
        stacklevel=2,
    )
    model_lower = model_id.lower()
    
    # Check patterns in order of specificity
    # More specific patterns should be checked first
    ordered_patterns = [
        ("gpt-4-turbo", 128000),
        ("gpt-4o-mini", 128000),
        ("gpt-4o", 128000),
        ("gpt-4-32k", 32768),
        ("gpt-4", 8192),
        ("claude-3-5-sonnet", 200000),
        ("claude-3-5-haiku", 200000),
        ("claude-3-opus", 200000),
        ("claude-3-sonnet", 200000),
        ("claude-3-haiku", 200000),
        ("gemini-1.5-pro", 1048576),
        ("gemini-1.5-flash", 1048576),
        ("gemini-pro", 32760),
        ("gpt-3.5-turbo", 16385),
        ("llama-3-70b", 8192),
        ("llama-2-70b", 4096),
        ("mistral-large", 32000),
        ("codellama-34b", 16384),
    ]
    
    for pattern, limit in ordered_patterns:
        if pattern in model_lower:
            return limit
    
    return 0


def validate_model_identity(identity: ModelIdentity) -> tuple[bool, str]:
    """Validate model identity for completeness.
    
    Returns:
        (valid, reason) - valid=True if identity is complete enough for evidence
        
    Note: This validates completeness, not trustworthiness.
    Use identity.is_trusted_for_audit() to check if identity is trusted.
    """
    if not identity.provider:
        return False, "MISSING_PROVIDER"
    
    if not identity.model_id:
        return False, "MISSING_MODEL_ID"
    
    if identity.context_limit <= 0:
        return False, "UNKNOWN_CONTEXT_LIMIT"
    
    if identity.temperature < 0.0 or identity.temperature > 2.0:
        return False, "INVALID_TEMPERATURE"
    
    if identity.source == "unresolved":
        return False, "UNRESOLVED_SOURCE"
    
    return True, "OK"
