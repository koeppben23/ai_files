"""Infrastructure adapter for resolving phase5 policy config path."""

from __future__ import annotations

from pathlib import Path


class CanonicalRootPhase5ConfigResolver:
    """Resolver that uses canonical root binding for phase5 config."""

    def __init__(self, mode: str = "user"):
        self._mode = mode

    def resolve_config_path(self) -> Path | None:
        try:
            from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver

            resolver = BindingEvidenceResolver()
            evidence = resolver.resolve(mode=self._mode)
            if evidence.binding_ok and evidence.commands_home:
                canonical_path = evidence.commands_home / "governance" / "assets" / "config" / "phase5_review_config.yaml"
                if canonical_path.exists():
                    return canonical_path
        except Exception:
            if self._mode == "pipeline":
                return None
        return None

    def operating_mode(self) -> str:
        return self._mode


def configure_phase5_review_resolver(mode: str = "user") -> None:
    from governance_runtime.application.use_cases.phase5_review_config import set_config_path_resolver

    set_config_path_resolver(CanonicalRootPhase5ConfigResolver(mode=mode))
