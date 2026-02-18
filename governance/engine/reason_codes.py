"""Backward-compatible reason code import surface.

Canonical constants live in `governance.domain.reason_codes`.
"""

from governance.domain.reason_codes import *  # noqa: F401,F403

# Keep explicit compatibility bindings for build/readme scanners.
from governance.domain.reason_codes import (  # noqa: F401
    NOT_VERIFIED_EVIDENCE_STALE as _NOT_VERIFIED_EVIDENCE_STALE,
    NOT_VERIFIED_MISSING_EVIDENCE as _NOT_VERIFIED_MISSING_EVIDENCE,
)

NOT_VERIFIED_EVIDENCE_STALE = _NOT_VERIFIED_EVIDENCE_STALE
NOT_VERIFIED_MISSING_EVIDENCE = _NOT_VERIFIED_MISSING_EVIDENCE
