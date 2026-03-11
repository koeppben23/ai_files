"""Canonical operating-profile resolution for governance runtime.

Profiles are monotonic and represent governance hardness:
``solo < team < regulated``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OperatingProfile = Literal["solo", "team", "regulated"]

UNKNOWN_PROFILE = "UNKNOWN_PROFILE"
INVALID_PROFILE_CONFLICT = "INVALID_PROFILE_CONFLICT"
FORBIDDEN_DOWNSHIFT = "FORBIDDEN_DOWNSHIFT"
UNTRUSTED_ENFORCEMENT_SOURCE = "UNTRUSTED_ENFORCEMENT_SOURCE"
MISSING_OPERATING_MODE = "MISSING_OPERATING_MODE"
PROFILE_FLOOR_VIOLATION = "PROFILE_FLOOR_VIOLATION"

_PROFILE_ORDER: dict[OperatingProfile, int] = {
    "solo": 1,
    "team": 2,
    "regulated": 3,
}

_PROFILE_ALIASES: dict[str, OperatingProfile] = {
    "solo": "solo",
    "team": "team",
    "regulated": "regulated",
    # backward-compatible aliases
    "user": "solo",
    "pipeline": "team",
    "agents_strict": "regulated",
    "system": "team",
}

_TRUSTED_ENFORCEMENT_SOURCES: frozenset[str] = frozenset(
    {
        "ci",
        "pipeline",
        "protected-pipeline",
        "repo-policy",
        "org-policy",
    }
)


class OperatingProfileError(ValueError):
    """Raised when operating-profile resolution fails closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OperatingProfileResolution:
    requested_operating_mode: OperatingProfile | None
    repo_operating_mode: OperatingProfile
    init_operating_mode: OperatingProfile
    enforced_operating_mode: OperatingProfile | None
    resolved_operating_mode: OperatingProfile
    floor_operating_mode: OperatingProfile | None


def normalize_operating_profile(mode: str | None) -> OperatingProfile | None:
    if mode is None:
        return None
    token = str(mode).strip().lower()
    if not token:
        return None
    return _PROFILE_ALIASES.get(token)


def max_operating_profile(*modes: OperatingProfile | None) -> OperatingProfile:
    present: list[OperatingProfile] = [m for m in modes if m is not None]
    if not present:
        raise OperatingProfileError(MISSING_OPERATING_MODE, "No operating profile inputs provided")
    winner = present[0]
    for candidate in present[1:]:
        if _PROFILE_ORDER[candidate] > _PROFILE_ORDER[winner]:
            winner = candidate
    return winner


def is_downshift(current: OperatingProfile, requested: OperatingProfile) -> bool:
    return _PROFILE_ORDER[requested] < _PROFILE_ORDER[current]


def meets_floor(resolved: OperatingProfile, floor: OperatingProfile | None) -> bool:
    if floor is None:
        return True
    return _PROFILE_ORDER[resolved] >= _PROFILE_ORDER[floor]


def is_trusted_enforcement_source(source: str | None) -> bool:
    if source is None:
        return False
    return str(source).strip().lower() in _TRUSTED_ENFORCEMENT_SOURCES


def resolve_operating_profile(
    *,
    requested_operating_mode: str | None,
    repo_operating_mode: str | None,
    init_operating_mode: str | None,
    enforced_operating_mode: str | None,
    enforced_source: str | None,
    floor_operating_mode: str | None,
) -> OperatingProfileResolution:
    requested = normalize_operating_profile(requested_operating_mode)
    repo_default = normalize_operating_profile(repo_operating_mode)
    init_default = normalize_operating_profile(init_operating_mode)
    enforced = normalize_operating_profile(enforced_operating_mode)
    floor = normalize_operating_profile(floor_operating_mode)

    if requested_operating_mode and requested is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown requested profile: {requested_operating_mode}")
    if repo_operating_mode and repo_default is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown repo profile: {repo_operating_mode}")
    if init_operating_mode and init_default is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown init profile: {init_operating_mode}")
    if enforced_operating_mode and enforced is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown enforced profile: {enforced_operating_mode}")
    if floor_operating_mode and floor is None:
        raise OperatingProfileError(UNKNOWN_PROFILE, f"Unknown floor profile: {floor_operating_mode}")

    if repo_default is None and init_default is None:
        raise OperatingProfileError(MISSING_OPERATING_MODE, "Repo/init defaults missing")

    trusted_enforcement = enforced if (enforced is not None and is_trusted_enforcement_source(enforced_source)) else None
    if enforced is not None and trusted_enforcement is None:
        strict_mode = max_operating_profile(repo_default, init_default, floor) == "regulated"
        if strict_mode:
            raise OperatingProfileError(
                UNTRUSTED_ENFORCEMENT_SOURCE,
                "Regulated profile requires trusted enforcement source",
            )

    base = max_operating_profile(repo_default, init_default)
    resolved = max_operating_profile(base, trusted_enforcement, requested)

    if requested is not None and is_downshift(base, requested):
        raise OperatingProfileError(FORBIDDEN_DOWNSHIFT, "Requested profile downshifts below baseline")

    if floor is not None and not meets_floor(resolved, floor):
        raise OperatingProfileError(
            PROFILE_FLOOR_VIOLATION,
            f"Resolved profile {resolved} does not meet floor {floor}",
        )

    if trusted_enforcement is not None and is_downshift(trusted_enforcement, resolved):
        raise OperatingProfileError(INVALID_PROFILE_CONFLICT, "Resolved profile conflicts with enforced profile")

    resolved_repo_mode = repo_default if repo_default is not None else init_default
    resolved_init_mode = init_default if init_default is not None else repo_default
    if resolved_repo_mode is None or resolved_init_mode is None:
        raise OperatingProfileError(MISSING_OPERATING_MODE, "Repo/init defaults missing")

    return OperatingProfileResolution(
        requested_operating_mode=requested,
        repo_operating_mode=resolved_repo_mode,
        init_operating_mode=resolved_init_mode,
        enforced_operating_mode=trusted_enforcement,
        resolved_operating_mode=resolved,
        floor_operating_mode=floor,
    )
