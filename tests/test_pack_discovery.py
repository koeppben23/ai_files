from __future__ import annotations

import pytest

from governance.packs.discovery import (
    activate_candidates,
    collect_discovered_candidates,
    resolve_trust_policy,
)


def _manifest(pack_id: str, version: str, marker: str) -> dict:
    """Build test manifest with source marker to verify selection behavior."""

    return {
        "id": pack_id,
        "version": version,
        "compat": {"engine_min": "1.0.0", "engine_max": "9.9.9"},
        "requires": [],
        "conflicts_with": [],
        "marker": marker,
    }


@pytest.mark.governance
def test_collect_discovery_order_is_workspace_then_installer_then_user():
    """Discovery list should preserve deterministic source collection order."""

    discovered = collect_discovered_candidates(
        workspace_candidates=[_manifest("core", "1.0.0", "workspace")],
        installer_candidates=[_manifest("core", "1.0.0", "installer")],
        user_candidates=[_manifest("core", "1.0.0", "user")],
    )
    assert [item.source for item in discovered] == ["workspace", "installer", "user"]


@pytest.mark.governance
def test_activation_prefers_installer_source_over_discovery_order_when_workspace_disabled():
    """Activation should use trust/activation precedence, not discovery order."""

    discovered = collect_discovered_candidates(
        workspace_candidates=[_manifest("core", "1.0.0", "workspace")],
        installer_candidates=[_manifest("core", "1.0.0", "installer")],
        user_candidates=[_manifest("core", "1.0.0", "user")],
    )
    policy = resolve_trust_policy(repo_policy=None, global_policy=None, runtime_override=None)
    activated = activate_candidates(discovered=discovered, trust_policy=policy)
    assert activated["core"]["marker"] == "installer"
    assert activated["core"]["source"] == "installer"
    assert activated["core"]["policy_source"] == "default"


@pytest.mark.governance
def test_activation_keeps_trust_precedence_even_when_workspace_override_is_enabled():
    """Workspace enablement should not bypass installer/user trust precedence."""

    discovered = collect_discovered_candidates(
        workspace_candidates=[_manifest("core", "1.0.0", "workspace")],
        installer_candidates=[],
        user_candidates=[_manifest("core", "1.0.0", "user")],
    )
    policy = resolve_trust_policy(
        repo_policy={"workspace_overrides_enabled": True},
        global_policy={"workspace_overrides_enabled": False},
        runtime_override=False,
    )
    activated = activate_candidates(discovered=discovered, trust_policy=policy)
    assert activated["core"]["marker"] == "user"
    assert activated["core"]["source"] == "user"
    assert activated["core"]["policy_source"] == "repo-policy"


@pytest.mark.governance
def test_trust_policy_precedence_is_repo_then_global_then_runtime():
    """Repo/global/runtime precedence should be deterministic and strict."""

    repo_wins = resolve_trust_policy(
        repo_policy={"workspace_overrides_enabled": False},
        global_policy={"workspace_overrides_enabled": True},
        runtime_override=True,
    )
    assert repo_wins.workspace_overrides_enabled is False
    assert repo_wins.policy_source == "repo-policy"

    global_wins = resolve_trust_policy(
        repo_policy=None,
        global_policy={"workspace_overrides_enabled": True},
        runtime_override=False,
    )
    assert global_wins.workspace_overrides_enabled is True
    assert global_wins.policy_source == "global-policy"

    runtime_used = resolve_trust_policy(repo_policy=None, global_policy=None, runtime_override=True)
    assert runtime_used.workspace_overrides_enabled is True
    assert runtime_used.policy_source == "runtime-override"


@pytest.mark.governance
def test_activation_fails_closed_when_no_source_is_trust_allowed():
    """Activation should fail closed when only disallowed workspace candidates exist."""

    discovered = collect_discovered_candidates(
        workspace_candidates=[_manifest("core", "1.0.0", "workspace")],
        installer_candidates=[],
        user_candidates=[],
    )
    policy = resolve_trust_policy(repo_policy=None, global_policy=None, runtime_override=False)
    with pytest.raises(ValueError, match="no trust-allowed candidate"):
        activate_candidates(discovered=discovered, trust_policy=policy)
