"""Wave B runtime gate for engine activation.

This module starts Wave B by composing state-machine and gate-evaluator outputs
behind an explicit selfcheck gate. Default behavior remains shadow-mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from governance.engine.gate_evaluator import GateEvaluation, evaluate_gate
from governance.engine.reason_codes import BLOCKED_ENGINE_SELFCHECK, REASON_CODE_NONE, WARN_ENGINE_LIVE_DENIED
from governance.engine.selfcheck import EngineSelfcheckResult, run_engine_selfcheck
from governance.engine.state_machine import EngineState, build_state

EngineRuntimeMode = Literal["shadow", "live"]
LiveEnablePolicy = Literal["ci_strict", "auto_degrade"]


@dataclass(frozen=True)
class EngineRuntimeDecision:
    """Engine runtime activation decision with derived boundary artifacts."""

    runtime_mode: EngineRuntimeMode
    state: EngineState
    gate: GateEvaluation
    reason_code: str
    selfcheck: EngineSelfcheckResult
    deviation_code: str


def golden_parity_fields(
    decision: EngineRuntimeDecision,
    *,
    blocked_next_command: str = "/start",
    ok_next_command: str = "none",
) -> dict[str, str]:
    """Extract semantic parity fields used by Wave B golden checks.

    The returned fields align with the baseline parity contract:
    `status`, `phase`, `reason_code`, and `next_action.command`.

    Status is canonicalized to `blocked|ok` for deterministic parity snapshots.
    """

    runtime_blocked = decision.reason_code.startswith("BLOCKED-")
    gate_blocked = decision.gate.status == "blocked"
    blocked = runtime_blocked or gate_blocked
    reason_code = decision.reason_code
    if reason_code == REASON_CODE_NONE and gate_blocked:
        reason_code = decision.gate.reason_code

    return {
        "status": "blocked" if blocked else "ok",
        "phase": decision.state.phase,
        "reason_code": reason_code,
        "next_action.command": blocked_next_command if blocked else ok_next_command,
    }


def evaluate_runtime_activation(
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
    gate_key: str,
    gate_blocked: bool,
    gate_reason_code: str = REASON_CODE_NONE,
    enforce_registered_reason_code: bool = False,
    enable_live_engine: bool = False,
    live_enable_policy: LiveEnablePolicy = "ci_strict",
    selfcheck_result: EngineSelfcheckResult | None = None,
) -> EngineRuntimeDecision:
    """Compose Wave B runtime activation decision deterministically.

    Live mode is allowed only when `enable_live_engine=True` and selfcheck passes.
    Otherwise runtime remains in shadow mode with explicit reason code.
    """

    if live_enable_policy not in ("ci_strict", "auto_degrade"):
        raise ValueError("live_enable_policy must be one of: ci_strict, auto_degrade")

    state = build_state(
        phase=phase,
        active_gate=active_gate,
        mode=mode,
        next_gate_condition=next_gate_condition,
    )
    gate = evaluate_gate(
        gate_key=gate_key,
        blocked=gate_blocked,
        reason_code=gate_reason_code,
        enforce_registered_reason_code=enforce_registered_reason_code,
    )

    check = selfcheck_result if selfcheck_result is not None else run_engine_selfcheck()
    if enable_live_engine and check.ok:
        return EngineRuntimeDecision(
            runtime_mode="live",
            state=state,
            gate=gate,
            reason_code=REASON_CODE_NONE,
            selfcheck=check,
            deviation_code=REASON_CODE_NONE,
        )

    reason = REASON_CODE_NONE
    deviation = REASON_CODE_NONE
    if enable_live_engine and not check.ok:
        if live_enable_policy == "auto_degrade":
            reason = WARN_ENGINE_LIVE_DENIED
            deviation = "DEVIATION-ENGINE-LIVE-DENIED"
        else:
            reason = BLOCKED_ENGINE_SELFCHECK
    return EngineRuntimeDecision(
        runtime_mode="shadow",
        state=state,
        gate=gate,
        reason_code=reason,
        selfcheck=check,
        deviation_code=deviation,
    )
