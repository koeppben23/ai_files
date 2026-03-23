"""Policy mode domain model and principal_strict derivation.

``PolicyMode`` is an enforcement-mode flag orthogonal to ``OperatingMode``.
``resolve_principal_strict()`` determines whether the strict-exit pipeline
is active, using fail-closed OR-logic across configuration sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyMode:
    """Enforcement mode flags orthogonal to OperatingMode.

    ``principal_strict`` activates the strict-exit enforcement pipeline:
    critical criteria with missing/stale/below-threshold evidence -> BLOCKED.

    Derived via ``resolve_principal_strict()`` (fail-closed: any True source -> True).
    NOT coupled to addon load status.
    """

    principal_strict: bool = False


def resolve_principal_strict(
    *,
    profile_strict: bool | None = None,
    override_strict: bool | None = None,
    policy_strict: bool | None = None,
) -> bool:
    """Derive the effective ``principal_strict`` flag.

    Fail-closed OR-logic: if any source is True, result is True.

        1. ``policy_strict``  -- tenant-level policy override
        2. ``override_strict`` -- session/operator override
        3. ``profile_strict``  -- profile-level default

    This is intentionally NOT coupled to addon load status -- if strict is
    requested but required addons are missing, the gate will BLOCK
    (not silently downgrade).
    """
    sources = [s for s in (policy_strict, override_strict, profile_strict) if s is not None]
    if not sources:
        return False
    # Fail-closed: any True -> True
    return any(sources)
