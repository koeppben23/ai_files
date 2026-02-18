from __future__ import annotations

from typing import Any

from governance.packs.discovery import (
    PackCandidate,
    TrustPolicy,
    collect_discovered_candidates,
    resolve_trust_policy,
    select_activated_candidates,
)


class PackService:
    """Application-facing facade for pack discovery and activation."""

    def resolve_candidates(
        self,
        *,
        workspace_candidates: list[dict[str, Any]],
        installer_candidates: list[dict[str, Any]],
        user_candidates: list[dict[str, Any]],
    ) -> list[PackCandidate]:
        return collect_discovered_candidates(
            workspace_candidates=workspace_candidates,
            installer_candidates=installer_candidates,
            user_candidates=user_candidates,
        )

    def resolve_trust_policy(
        self,
        *,
        repo_policy: dict[str, Any] | None,
        global_policy: dict[str, Any] | None,
        runtime_override: bool | None,
    ) -> TrustPolicy:
        return resolve_trust_policy(
            repo_policy=repo_policy,
            global_policy=global_policy,
            runtime_override=runtime_override,
        )

    def activate(self, *, candidates: list[PackCandidate], trust_policy: TrustPolicy) -> list[PackCandidate]:
        return select_activated_candidates(candidates=candidates, trust_policy=trust_policy)
