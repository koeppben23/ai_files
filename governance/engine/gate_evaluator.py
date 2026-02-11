"""Gate evaluation boundary model for Wave A.

The evaluator contract is deterministic and side-effect free so existing
behavior remains unchanged until explicit engine activation in later waves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from governance.engine.reason_codes import BLOCKED_UNSPECIFIED, REASON_CODE_NONE

GateStatus = Literal["blocked", "warn", "ok", "not_verified"]


@dataclass(frozen=True)
class GateEvaluation:
    """Result contract for one gate evaluation."""

    gate_key: str
    status: GateStatus
    reason_code: str


def evaluate_gate(*, gate_key: str, blocked: bool, reason_code: str = REASON_CODE_NONE) -> GateEvaluation:
    """Build deterministic gate evaluation output from explicit inputs."""

    normalized_key = gate_key.strip()
    if blocked:
        rc = reason_code.strip() or BLOCKED_UNSPECIFIED
        return GateEvaluation(gate_key=normalized_key, status="blocked", reason_code=rc)
    return GateEvaluation(gate_key=normalized_key, status="ok", reason_code=REASON_CODE_NONE)
