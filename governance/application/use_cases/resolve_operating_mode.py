"""Operating mode resolution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from governance.application.ports.gateways import HostAdapter, OperatingMode


def resolve_effective_operating_mode(adapter: "HostAdapter", requested: "OperatingMode | None") -> "OperatingMode":
    """Resolve operating mode with deterministic precedence."""

    if requested is not None:
        return requested
    env = adapter.environment()
    ci = str(env.get("CI", "")).strip().lower()
    if ci and ci not in {"0", "false", "no", "off"}:
        return "pipeline"
    return adapter.default_operating_mode()


def has_required_mode_capabilities(mode: "OperatingMode", caps: Any) -> bool:
    """Return True when minimal capabilities for the requested mode are satisfied."""

    if mode == "user":
        return caps.fs_read_commands_home and caps.fs_write_workspaces_home
    if mode == "system":
        return caps.exec_allowed and caps.fs_read_commands_home and caps.fs_write_workspaces_home
    return (
        caps.exec_allowed
        and caps.fs_read_commands_home
        and caps.fs_write_workspaces_home
        and caps.fs_write_commands_home
        and caps.git_available
    )
