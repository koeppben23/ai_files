"""Infrastructure adapter for resolving policy config path.

This module belongs in infrastructure layer and implements the
ConfigPathResolver protocol defined in application layer.
"""

from __future__ import annotations

from pathlib import Path


class CanonicalRootConfigResolver:
    """Resolver that uses canonical root binding."""
    
    def __init__(self, mode: str = "user"):
        self._mode = mode
    
    def resolve_config_path(self) -> Path | None:
        """Resolve from canonical root (governance.paths.json)."""
        try:
            from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
            resolver = BindingEvidenceResolver()
            evidence = resolver.resolve(mode=self._mode)
            if evidence.binding_ok and evidence.commands_home:
                canonical_path = evidence.commands_home / "governance" / "assets" / "config" / "phase4_self_review_config.yaml"
                if canonical_path.exists():
                    return canonical_path
        except Exception:
            if self._mode == "pipeline":
                return None
        return None

    def operating_mode(self) -> str:
        return self._mode


def configure_phase4_self_review_resolver(mode: str = "user") -> None:
    """Configure the phase4_self_review module with infrastructure resolver."""
    from governance_runtime.application.use_cases.phase4_self_review import set_config_path_resolver
    set_config_path_resolver(CanonicalRootConfigResolver(mode=mode))
