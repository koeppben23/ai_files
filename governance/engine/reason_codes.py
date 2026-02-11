"""Canonical governance reason-code registry.

Wave A keeps behavior parity: values in this module must match currently emitted
runtime reason codes until a deliberate migration updates both emitters and tests.
"""

from __future__ import annotations

from typing import Final

# Sentinel used when a gate has no blocking/warning reason.
REASON_CODE_NONE: Final[str] = "none"

# Blocking reason codes.
BLOCKED_MISSING_BINDING_FILE: Final[str] = "BLOCKED-MISSING-BINDING-FILE"
BLOCKED_VARIABLE_RESOLUTION: Final[str] = "BLOCKED-VARIABLE-RESOLUTION"
BLOCKED_WORKSPACE_PERSISTENCE: Final[str] = "BLOCKED-WORKSPACE-PERSISTENCE"
BLOCKED_ENGINE_SELFCHECK: Final[str] = "BLOCKED-ENGINE-SELFCHECK"
BLOCKED_STATE_OUTDATED: Final[str] = "BLOCKED-STATE-OUTDATED"
BLOCKED_UNSPECIFIED: Final[str] = "BLOCKED-UNSPECIFIED"
BLOCKED_PERSISTENCE_TARGET_DEGENERATE: Final[str] = "BLOCKED-PERSISTENCE-TARGET-DEGENERATE"
BLOCKED_PERSISTENCE_PATH_VIOLATION: Final[str] = "BLOCKED-PERSISTENCE-PATH-VIOLATION"

# Warning reason codes.
WARN_UNMAPPED_AUDIT_REASON: Final[str] = "WARN-UNMAPPED-AUDIT-REASON"
WARN_WORKSPACE_PERSISTENCE: Final[str] = "WARN-WORKSPACE-PERSISTENCE"
WARN_ENGINE_LIVE_DENIED: Final[str] = "WARN-ENGINE-LIVE-DENIED"

# Default used by audit reason-code bridging when a key is not explicitly mapped.
DEFAULT_UNMAPPED_AUDIT_REASON: Final[str] = WARN_UNMAPPED_AUDIT_REASON

# Flat canonical set for validation and parity checks.
CANONICAL_REASON_CODES: Final[tuple[str, ...]] = (
    BLOCKED_MISSING_BINDING_FILE,
    BLOCKED_VARIABLE_RESOLUTION,
    BLOCKED_WORKSPACE_PERSISTENCE,
    BLOCKED_ENGINE_SELFCHECK,
    BLOCKED_STATE_OUTDATED,
    BLOCKED_UNSPECIFIED,
    BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
    BLOCKED_PERSISTENCE_PATH_VIOLATION,
    WARN_UNMAPPED_AUDIT_REASON,
    WARN_WORKSPACE_PERSISTENCE,
    WARN_ENGINE_LIVE_DENIED,
)


def is_registered_reason_code(reason_code: str, *, allow_none: bool = True) -> bool:
    """Return True if the reason code is in the canonical registry.

    `none` is accepted by default because it is used as a deterministic
    non-blocking sentinel in boundary contracts.
    """

    normalized = reason_code.strip()
    if allow_none and normalized == REASON_CODE_NONE:
        return True
    return normalized in CANONICAL_REASON_CODES
