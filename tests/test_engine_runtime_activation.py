from __future__ import annotations

import pytest

from governance.engine.reason_codes import BLOCKED_ENGINE_SELFCHECK, REASON_CODE_NONE
from governance.engine.runtime import evaluate_runtime_activation
from governance.engine.selfcheck import EngineSelfcheckResult, run_engine_selfcheck


@pytest.mark.governance
def test_runtime_activation_defaults_to_shadow_mode():
    """Wave B runtime should remain shadow-mode when live mode is not requested."""

    decision = evaluate_runtime_activation(
        phase="4-Implement-Ready",
        active_gate="Scope/Task selection",
        mode="OK",
        next_gate_condition="Concrete implementation target is defined",
        gate_key="P4-Entry",
        gate_blocked=False,
    )
    assert decision.runtime_mode == "shadow"
    assert decision.reason_code == REASON_CODE_NONE
    assert decision.selfcheck.ok is True


@pytest.mark.governance
def test_runtime_activation_blocks_live_mode_on_failed_selfcheck():
    """Live activation must fail-closed when selfcheck does not pass."""

    failed = EngineSelfcheckResult(ok=False, failed_checks=("reason_code_registry_has_duplicates",))
    decision = evaluate_runtime_activation(
        phase="4-Implement-Ready",
        active_gate="Scope/Task selection",
        mode="OK",
        next_gate_condition="Concrete implementation target is defined",
        gate_key="P4-Entry",
        gate_blocked=False,
        enable_live_engine=True,
        selfcheck_result=failed,
    )
    assert decision.runtime_mode == "shadow"
    assert decision.reason_code == BLOCKED_ENGINE_SELFCHECK


@pytest.mark.governance
def test_runtime_activation_enters_live_mode_when_selfcheck_passes():
    """Live activation is allowed when explicitly enabled and selfcheck passes."""

    passing = EngineSelfcheckResult(ok=True, failed_checks=())
    decision = evaluate_runtime_activation(
        phase="4-Implement-Ready",
        active_gate="Scope/Task selection",
        mode="OK",
        next_gate_condition="Concrete implementation target is defined",
        gate_key="P4-Entry",
        gate_blocked=False,
        enable_live_engine=True,
        selfcheck_result=passing,
    )
    assert decision.runtime_mode == "live"
    assert decision.reason_code == REASON_CODE_NONE


@pytest.mark.governance
def test_engine_selfcheck_passes_with_current_registry():
    """Current baseline registry should satisfy Wave B selfcheck checks."""

    result = run_engine_selfcheck()
    assert result.ok is True
    assert result.failed_checks == ()
