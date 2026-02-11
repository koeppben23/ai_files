"""Canonical surface policy matrix for mode and capability enforcement.

This module centralizes canonical target-variable -> surface policy mapping so
mode/capability checks are declarative and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from governance.engine.adapters import HostCapabilities, OperatingMode

SurfaceCapabilityKey = Literal[
    "fs_write_workspaces_home",
    "fs_write_commands_home",
    "fs_write_config_root",
    "fs_write_repo_root",
]


@dataclass(frozen=True)
class SurfacePolicy:
    """Policy contract for one canonical write-target variable."""

    target_variable: str
    capability_key: SurfaceCapabilityKey
    minimum_mode: OperatingMode


_MODE_ORDER: dict[OperatingMode, int] = {
    "user": 1,
    "system": 2,
    "pipeline": 3,
}

_SURFACE_POLICY: dict[str, SurfacePolicy] = {
    "WORKSPACE_MEMORY_FILE": SurfacePolicy("WORKSPACE_MEMORY_FILE", "fs_write_workspaces_home", "user"),
    "SESSION_STATE_FILE": SurfacePolicy("SESSION_STATE_FILE", "fs_write_workspaces_home", "user"),
    "REPO_CACHE_FILE": SurfacePolicy("REPO_CACHE_FILE", "fs_write_workspaces_home", "user"),
    "REPO_DECISION_PACK_FILE": SurfacePolicy("REPO_DECISION_PACK_FILE", "fs_write_workspaces_home", "user"),
    "REPO_DIGEST_FILE": SurfacePolicy("REPO_DIGEST_FILE", "fs_write_workspaces_home", "user"),
    "COMMANDS_HOME": SurfacePolicy("COMMANDS_HOME", "fs_write_commands_home", "system"),
    "PROFILES_HOME": SurfacePolicy("PROFILES_HOME", "fs_write_commands_home", "system"),
    "SESSION_STATE_POINTER_FILE": SurfacePolicy("SESSION_STATE_POINTER_FILE", "fs_write_commands_home", "pipeline"),
    "CONFIG_ROOT": SurfacePolicy("CONFIG_ROOT", "fs_write_config_root", "user"),
    "OPENCODE_HOME": SurfacePolicy("OPENCODE_HOME", "fs_write_config_root", "user"),
    "WORKSPACES_HOME": SurfacePolicy("WORKSPACES_HOME", "fs_write_config_root", "user"),
    "REPO_HOME": SurfacePolicy("REPO_HOME", "fs_write_repo_root", "user"),
    "REPO_BUSINESS_RULES_FILE": SurfacePolicy("REPO_BUSINESS_RULES_FILE", "fs_write_repo_root", "user"),
}


def resolve_surface_policy(target_variable: str) -> SurfacePolicy | None:
    """Return surface policy for one canonical target variable."""

    return _SURFACE_POLICY.get(target_variable)


def mode_satisfies_requirement(*, effective_mode: OperatingMode, minimum_mode: OperatingMode) -> bool:
    """Return True when effective mode satisfies required minimum mode."""

    return _MODE_ORDER[effective_mode] >= _MODE_ORDER[minimum_mode]


def capability_satisfies_requirement(*, caps: HostCapabilities, capability_key: SurfaceCapabilityKey) -> bool:
    """Return True when host capabilities satisfy required surface capability."""

    return bool(getattr(caps, capability_key))
