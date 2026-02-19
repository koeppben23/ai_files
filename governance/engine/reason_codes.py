"""Backward-compatible reason code import surface.

Canonical constants live in `governance.domain.reason_codes`.
This module re-exports everything for legacy import paths.
"""

from governance.domain.reason_codes import *  # noqa: F401,F403

from governance.domain.reason_codes import (  # noqa: F401
    BLOCKED_P5_3_TEST_QUALITY_GATE,
    BLOCKED_P5_4_BUSINESS_RULES_GATE,
    BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
    BLOCKED_P6_PREREQUISITES_NOT_MET,
    BLOCKED_UNSPECIFIED,
    NOT_VERIFIED_EVIDENCE_STALE,
    NOT_VERIFIED_MISSING_EVIDENCE,
    REASON_CODE_NONE,
    is_registered_reason_code,
)
