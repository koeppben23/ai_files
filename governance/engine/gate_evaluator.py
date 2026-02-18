"""Gate evaluation boundary model for Wave A.

The evaluator contract is deterministic and side-effect free so existing
behavior remains unchanged until explicit engine activation in later waves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from governance.engine.reason_codes import (
    BLOCKED_UNSPECIFIED,
    REASON_CODE_NONE,
    is_registered_reason_code,
)

GateStatus = Literal["blocked", "warn", "ok", "not_verified"]


@dataclass(frozen=True)
class GateEvaluation:
    """Result contract for one gate evaluation."""

    gate_key: str
    status: GateStatus
    reason_code: str


def evaluate_gate(
    *,
    gate_key: str,
    blocked: bool,
    reason_code: str = REASON_CODE_NONE,
    enforce_registered_reason_code: bool = False,
) -> GateEvaluation:
    """Build deterministic gate evaluation output from explicit inputs.

    When `enforce_registered_reason_code=True`, the evaluator fail-closes unknown
    blocked reason codes to `BLOCKED-UNSPECIFIED`.
    """

    normalized_key = gate_key.strip()
    if blocked:
        rc = reason_code.strip() or BLOCKED_UNSPECIFIED
        if enforce_registered_reason_code and not is_registered_reason_code(rc, allow_none=False):
            rc = BLOCKED_UNSPECIFIED
        return GateEvaluation(gate_key=normalized_key, status="blocked", reason_code=rc)
    return GateEvaluation(gate_key=normalized_key, status="ok", reason_code=REASON_CODE_NONE)
