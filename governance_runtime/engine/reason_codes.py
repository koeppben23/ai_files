"""Backward-compatible reason code import surface.

Canonical constants live in `governance.domain.reason_codes`.
This module re-exports everything for legacy import paths.
"""

from governance_runtime.domain.reason_codes import *  # noqa: F401,F403

from governance_runtime.domain.reason_codes import (  # noqa: F401
    BLOCKED_P5_3_TEST_QUALITY_GATE,
    BLOCKED_P5_4_BUSINESS_RULES_GATE,
    BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
    BLOCKED_P5_PLAN_RECORD_PERSIST,
    BLOCKED_P6_PLAN_COMPLIANCE_MAJOR,
    BLOCKED_P6_PREREQUISITES_NOT_MET,
    BLOCKED_STRICT_CONTRACT_MISSING,
    BLOCKED_STRICT_EVIDENCE_MISSING,
    BLOCKED_STRICT_EVIDENCE_STALE,
    BLOCKED_STRICT_THRESHOLD,
    BLOCKED_UNSPECIFIED,
    NOT_VERIFIED_EVIDENCE_STALE,
    NOT_VERIFIED_MISSING_EVIDENCE,
    NOT_VERIFIED_STRICT_EVIDENCE_MISSING,
    NOT_VERIFIED_STRICT_EVIDENCE_STALE,
    REASON_CODE_NONE,
    WARN_P6_PLAN_COMPLIANCE_DRIFT,
    is_registered_reason_code,
)
