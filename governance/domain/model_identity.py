"""Model Identity - Evidence for reproducibility.

Model identity is critical for reproducibility and audit.
Every run MUST record which model produced the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    
    temperature: float = 0.0
    """Sampling temperature (0.0 = deterministic)"""
    
    version: str | None = None
    """Model version/snapshot if available"""
    
    quantization: str | None = None
    """Quantization level if applicable (e.g., '4bit', '8bit')"""
    
    deployment_id: str | None = None
    """Deployment/endpoint ID for enterprise models"""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "provider": self.provider,
            "model_id": self.model_id,
            "context_limit": self.context_limit,
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
    """
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
    """
    if not identity.provider:
        return False, "MISSING_PROVIDER"
    
    if not identity.model_id:
        return False, "MISSING_MODEL_ID"
    
    if identity.context_limit <= 0:
        # Try to infer
        inferred = infer_context_limit(identity.model_id)
        if inferred <= 0:
            return False, "UNKNOWN_CONTEXT_LIMIT"
    
    if identity.temperature < 0.0 or identity.temperature > 2.0:
        return False, "INVALID_TEMPERATURE"
    
    return True, "OK"
