"""Legacy compatibility bridge for repo root resolution.

DEPRECATED: use governance_runtime.infrastructure.repo_root_resolver.
"""

from governance_runtime.infrastructure.repo_root_resolver import (
    RepoRootResolutionResult,
    resolve_repo_root,
)

__all__ = ["RepoRootResolutionResult", "resolve_repo_root"]
