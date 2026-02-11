"""Canonical governance reason-code registry.

Wave A keeps behavior parity: values in this module must match currently emitted
runtime reason codes until a deliberate migration updates both emitters and tests.
"""

from __future__ import annotations

from typing import Final

# Blocking reason codes.
BLOCKED_MISSING_BINDING_FILE: Final[str] = "BLOCKED-MISSING-BINDING-FILE"
BLOCKED_VARIABLE_RESOLUTION: Final[str] = "BLOCKED-VARIABLE-RESOLUTION"
BLOCKED_WORKSPACE_PERSISTENCE: Final[str] = "BLOCKED-WORKSPACE-PERSISTENCE"

# Warning reason codes.
WARN_UNMAPPED_AUDIT_REASON: Final[str] = "WARN-UNMAPPED-AUDIT-REASON"
WARN_WORKSPACE_PERSISTENCE: Final[str] = "WARN-WORKSPACE-PERSISTENCE"

# Default used by audit reason-code bridging when a key is not explicitly mapped.
DEFAULT_UNMAPPED_AUDIT_REASON: Final[str] = WARN_UNMAPPED_AUDIT_REASON

# Flat canonical set for validation and parity checks.
CANONICAL_REASON_CODES: Final[tuple[str, ...]] = (
    BLOCKED_MISSING_BINDING_FILE,
    BLOCKED_VARIABLE_RESOLUTION,
    BLOCKED_WORKSPACE_PERSISTENCE,
    WARN_UNMAPPED_AUDIT_REASON,
    WARN_WORKSPACE_PERSISTENCE,
)
