from __future__ import annotations

import pytest

from governance.engine.adapters import HostCapabilities
from governance.engine.surface_policy import (
    capability_satisfies_requirement,
    mode_satisfies_requirement,
    resolve_surface_policy,
)


@pytest.mark.governance
def test_surface_policy_resolves_known_targets_deterministically():
    """Known canonical target variables should resolve to stable policy entries."""

    commands = resolve_surface_policy("COMMANDS_HOME")
    pointer = resolve_surface_policy("SESSION_STATE_POINTER_FILE")
    assert commands is not None
    assert commands.minimum_mode == "system"
    assert pointer is not None
    assert pointer.minimum_mode == "pipeline"


@pytest.mark.governance
def test_surface_policy_mode_order_enforces_user_system_pipeline():
    """Mode checks should preserve strict ordering semantics."""

    assert mode_satisfies_requirement(effective_mode="user", minimum_mode="user") is True
    assert mode_satisfies_requirement(effective_mode="system", minimum_mode="user") is True
    assert mode_satisfies_requirement(effective_mode="pipeline", minimum_mode="system") is True
    assert mode_satisfies_requirement(effective_mode="system", minimum_mode="pipeline") is False


@pytest.mark.governance
def test_surface_policy_capability_checks_use_declared_capability_key():
    """Capability checks should evaluate the mapped capability key directly."""

    caps = HostCapabilities(
        cwd_trust="trusted",
        fs_read_commands_home=True,
        fs_write_config_root=True,
        fs_write_commands_home=False,
        fs_write_workspaces_home=True,
        fs_write_repo_root=True,
        exec_allowed=True,
        git_available=True,
    )
    assert capability_satisfies_requirement(caps=caps, capability_key="fs_write_workspaces_home") is True
    assert capability_satisfies_requirement(caps=caps, capability_key="fs_write_commands_home") is False
