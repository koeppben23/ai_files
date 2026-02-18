"""Deterministic pack discovery and trust-gated activation for Wave C.

Discovery order is intentionally separate from activation precedence:
- discovery collects candidates from workspace/installer/user scopes,
- activation selects candidates using trust policy and source precedence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PackSource = Literal["workspace", "installer", "user"]

_DISCOVERY_ORDER: tuple[PackSource, ...] = ("workspace", "installer", "user")
_ACTIVATION_ORDER: tuple[PackSource, ...] = ("installer", "user", "workspace")


@dataclass(frozen=True)
class PackCandidate:
    """One discovered pack candidate from a specific source."""

    pack_id: str
    source: PackSource
    manifest: dict[str, Any]


@dataclass(frozen=True)
class TrustPolicy:
    """Resolved trust policy for pack activation."""

    workspace_overrides_enabled: bool
    policy_source: str


def _read_workspace_override_flag(data: dict[str, Any] | None) -> bool | None:
    """Read workspace override flag from policy payload when present."""

    if not isinstance(data, dict):
        return None
    value = data.get("workspace_overrides_enabled")
    if isinstance(value, bool):
        return value
    return None


def resolve_trust_policy(
    *,
    repo_policy: dict[str, Any] | None,
    global_policy: dict[str, Any] | None,
    runtime_override: bool | None,
) -> TrustPolicy:
    """Resolve trust policy using deterministic precedence.

    Precedence (highest first):
    1) repo policy
    2) global policy
    3) runtime override
    """

    repo_value = _read_workspace_override_flag(repo_policy)
    if repo_value is not None:
        return TrustPolicy(workspace_overrides_enabled=repo_value, policy_source="repo-policy")

    global_value = _read_workspace_override_flag(global_policy)
    if global_value is not None:
        return TrustPolicy(workspace_overrides_enabled=global_value, policy_source="global-policy")

    if runtime_override is not None:
        return TrustPolicy(workspace_overrides_enabled=runtime_override, policy_source="runtime-override")

    return TrustPolicy(workspace_overrides_enabled=False, policy_source="default")


def collect_discovered_candidates(
    *,
    workspace_candidates: list[dict[str, Any]],
    installer_candidates: list[dict[str, Any]],
    user_candidates: list[dict[str, Any]],
) -> list[PackCandidate]:
    """Collect discovered candidates in deterministic discovery order."""

    source_to_payload = {
        "workspace": workspace_candidates,
        "installer": installer_candidates,
        "user": user_candidates,
    }
    out: list[PackCandidate] = []
    for source in _DISCOVERY_ORDER:
        for item in source_to_payload[source]:
            if not isinstance(item, dict):
                raise ValueError(f"invalid candidate payload in {source} source")
            pack_id = item.get("id")
            if not isinstance(pack_id, str) or not pack_id.strip():
                raise ValueError(f"missing pack id in {source} source")
            out.append(PackCandidate(pack_id=pack_id.strip(), source=source, manifest=item))
    return out


def activate_candidates(
    *,
    discovered: list[PackCandidate],
    trust_policy: TrustPolicy,
) -> dict[str, dict[str, Any]]:
    """Activate one manifest per pack id using trust-gated source precedence."""

    grouped: dict[str, dict[PackSource, dict[str, Any]]] = {}
    for candidate in discovered:
        grouped.setdefault(candidate.pack_id, {})[candidate.source] = candidate.manifest

    allowed_sources = set(_ACTIVATION_ORDER)
    if not trust_policy.workspace_overrides_enabled:
        allowed_sources.remove("workspace")

    activated: dict[str, dict[str, Any]] = {}
    for pack_id in sorted(grouped):
        sources = grouped[pack_id]
        selected_manifest: dict[str, Any] | None = None
        selected_source: PackSource | None = None
        for source in _ACTIVATION_ORDER:
            if source not in allowed_sources:
                continue
            if source in sources:
                selected_source = source
                selected_manifest = sources[source]
                break
        if selected_manifest is None or selected_source is None:
            raise ValueError(f"no trust-allowed candidate available for pack {pack_id!r}")
        annotated = dict(selected_manifest)
        annotated["source"] = selected_source
        annotated["policy_source"] = trust_policy.policy_source
        activated[pack_id] = annotated
    return activated
