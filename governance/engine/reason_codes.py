"""Backward-compatible reason code import surface.

Canonical constants live in `governance.domain.reason_codes`.
This module re-exports everything for legacy import paths.
"""

from governance.domain.reason_codes import *  # noqa: F401,F403

# Explicit re-exports for tools that scan module members
from governance.domain.reason_codes import (  # noqa: F401
    NOT_VERIFIED_EVIDENCE_STALE,
    NOT_VERIFIED_MISSING_EVIDENCE,
    is_registered_reason_code,
)
