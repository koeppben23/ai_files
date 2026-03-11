"""Operating mode resolution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from governance.domain.operating_profile import OperatingProfileError, resolve_operating_profile

if TYPE_CHECKING:
    from governance.application.ports.gateways import HostAdapter, OperatingMode


_PROFILE_TO_RUNTIME_MODE: dict[str, "OperatingMode"] = {
    "solo": "user",
    "team": "pipeline",
    "regulated": "pipeline",
}


def _runtime_mode_to_profile(mode: str | None) -> str | None:
    if mode is None:
        return None
    token = str(mode).strip().lower()
    if not token:
        return None
    if token in {"solo", "team", "regulated", "user", "pipeline", "agents_strict", "system"}:
        return token
    return None


def _profile_to_runtime_mode(profile: str) -> "OperatingMode":
    return _PROFILE_TO_RUNTIME_MODE.get(profile, "user")


def resolve_effective_operating_mode(adapter: "HostAdapter", requested: "OperatingMode | None") -> "OperatingMode":
    """Resolve operating mode with deterministic precedence."""

    if requested is not None and requested not in {"user"}:
        return requested

    env = adapter.environment()
    has_profile_inputs = any(
        str(env.get(key, "")).strip()
        for key in (
            "OPENCODE_REPO_OPERATING_MODE",
            "OPENCODE_ENFORCE_PROFILE",
            "OPENCODE_PROFILE_FLOOR",
            "OPENCODE_OPERATING_PROFILE",
        )
    )

    if not has_profile_inputs:
        ci = str(env.get("CI", "")).strip().lower()
        if ci and ci not in {"0", "false", "no", "off"}:
            return "pipeline"
        return adapter.default_operating_mode()

    requested_profile = _runtime_mode_to_profile(requested)
    repo_profile = str(env.get("OPENCODE_REPO_OPERATING_MODE", "")).strip() or None
    init_profile = _runtime_mode_to_profile(adapter.default_operating_mode())

    enforced_profile = str(env.get("OPENCODE_ENFORCE_PROFILE", "")).strip() or None
    enforced_source = str(env.get("OPENCODE_ENFORCE_PROFILE_SOURCE", "")).strip() or None

    ci = str(env.get("CI", "")).strip().lower()
    if ci and ci not in {"0", "false", "no", "off"} and enforced_profile is None:
        enforced_profile = "team"
        enforced_source = enforced_source or "ci"

    floor_profile = str(env.get("OPENCODE_PROFILE_FLOOR", "")).strip() or None
    if ci and ci not in {"0", "false", "no", "off"} and floor_profile is None:
        floor_profile = "team"

    break_glass_expires_at = str(env.get("OPENCODE_BREAK_GLASS_EXPIRES_AT", "")).strip() or None
    break_glass_reason_code = str(env.get("OPENCODE_BREAK_GLASS_REASON_CODE", "")).strip() or None
    break_glass_now_utc = str(env.get("OPENCODE_CURRENT_TIME_UTC", "")).strip() or None

    try:
        resolved = resolve_operating_profile(
            requested_operating_mode=requested_profile,
            repo_operating_mode=repo_profile,
            init_operating_mode=init_profile,
            enforced_operating_mode=enforced_profile,
            enforced_source=enforced_source,
            floor_operating_mode=floor_profile,
            break_glass_expires_at=break_glass_expires_at,
            break_glass_reason_code=break_glass_reason_code,
            break_glass_now_utc=break_glass_now_utc,
        )
    except OperatingProfileError:
        return "pipeline"

    return _profile_to_runtime_mode(resolved.resolved_operating_mode)


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
