from __future__ import annotations

import pytest

from governance.engine.gate_evaluator import (
    evaluate_gate,
    evaluate_p53_test_quality_gate,
    evaluate_p54_business_rules_gate,
    evaluate_p56_rollback_safety_gate,
    evaluate_p6_prerequisites,
)
from governance.engine.reason_codes import (
    BLOCKED_P5_3_TEST_QUALITY_GATE,
    BLOCKED_P5_4_BUSINESS_RULES_GATE,
    BLOCKED_P5_6_ROLLBACK_SAFETY_GATE,
    BLOCKED_P6_PREREQUISITES_NOT_MET,
    BLOCKED_UNSPECIFIED,
    REASON_CODE_NONE,
)
from governance.engine.invariants import check_single_recovery_action
from governance.engine.state_machine import build_state, transition_to


@pytest.mark.governance
def test_state_machine_returns_same_object_for_no_delta_transition():
    """No-delta transitions should preserve object identity for later diffing."""

    state = build_state(
        phase="4-Implement-Ready",
        active_gate="Scope/Task selection",
        mode="OK",
        next_gate_condition="Concrete implementation target is defined",
    )
    transitioned = transition_to(
        state,
        phase=" 4-Implement-Ready ",
        active_gate=" Scope/Task selection ",
        mode=" OK ",
        next_gate_condition=" Concrete implementation target is defined ",
    )
    assert transitioned is state


@pytest.mark.governance
def test_gate_evaluator_emits_blocked_status_with_reason_code():
    """Blocked evaluations must carry an explicit reason code."""

    evaluation = evaluate_gate(gate_key="P5-Architecture", blocked=True, reason_code="BLOCKED-MISSING-EVIDENCE")
    assert evaluation.gate_key == "P5-Architecture"
    assert evaluation.status == "blocked"
    assert evaluation.reason_code == "BLOCKED-MISSING-EVIDENCE"


@pytest.mark.governance
def test_gate_evaluator_uses_registered_default_reason_codes():
    """Evaluator should use deterministic defaults for blocked and ok outputs."""

    blocked = evaluate_gate(gate_key="P5-Architecture", blocked=True, reason_code="")
    ok = evaluate_gate(gate_key="P5-Architecture", blocked=False)
    assert blocked.reason_code == BLOCKED_UNSPECIFIED
    assert ok.reason_code == REASON_CODE_NONE


@pytest.mark.governance
def test_gate_evaluator_can_enforce_registered_reason_codes():
    """Optional enforcement should fail-close unknown blocked reason codes."""

    evaluation = evaluate_gate(
        gate_key="P5-Architecture",
        blocked=True,
        reason_code="BLOCKED-NOT-REGISTERED",
        enforce_registered_reason_code=True,
    )
    assert evaluation.reason_code == BLOCKED_UNSPECIFIED


@pytest.mark.governance
def test_recovery_invariant_requires_primary_action_and_command():
    """Fail-closed recovery contract requires both fields to be non-empty."""

    assert check_single_recovery_action("Run /start", "/start").valid is True
    assert check_single_recovery_action("", "/start").valid is False
    assert check_single_recovery_action("Run /start", "").valid is False


@pytest.mark.governance
def test_p53_gate_blocks_when_test_strategy_missing():
    """P5.3 must block if Phase 4 plan has no Test Strategy subsection."""

    session_state = {"TicketRecordDigest": "Some plan without any testing section"}
    result = evaluate_p53_test_quality_gate(session_state=session_state)
    assert result.status == "fail"
    assert result.reason_code == BLOCKED_P5_3_TEST_QUALITY_GATE
    assert result.missing_test_strategy is True


@pytest.mark.governance
def test_p53_gate_passes_when_test_strategy_present():
    """P5.3 should pass when Test Strategy is in the plan."""

    session_state = {"TicketRecordDigest": "Phase 4 plan with Test Strategy subsection"}
    result = evaluate_p53_test_quality_gate(session_state=session_state)
    assert result.status == "pending"
    assert result.missing_test_strategy is False


@pytest.mark.governance
def test_p53_gate_respects_existing_pass_status():
    """P5.3 should respect already-passed gate status."""

    session_state = {
        "TicketRecordDigest": "Plan with Test Strategy",
        "Gates": {"P5.3-TestQuality": "pass"},
    }
    result = evaluate_p53_test_quality_gate(session_state=session_state)
    assert result.status == "pass"


@pytest.mark.governance
def test_p54_gate_not_applicable_when_phase_15_not_executed():
    """P5.4 is N/A if Phase 1.5 was not run."""

    session_state = {}
    result = evaluate_p54_business_rules_gate(session_state=session_state, phase_1_5_executed=False)
    assert result.status == "not-applicable"
    assert result.phase_1_5_executed is False


@pytest.mark.governance
def test_p54_gate_blocks_when_coverage_below_70_percent():
    """P5.4 must block if >30% business rules are uncovered."""

    session_state = {
        "BusinessRules": {
            "Rules": [
                {"id": "BR-1", "covered": True},
                {"id": "BR-2", "covered": False},
                {"id": "BR-3", "covered": False},
                {"id": "BR-4", "covered": False},
            ]
        }
    }
    result = evaluate_p54_business_rules_gate(session_state=session_state, phase_1_5_executed=True)
    assert result.status == "gap-detected"
    assert result.reason_code == BLOCKED_P5_4_BUSINESS_RULES_GATE
    assert result.total_business_rules == 4
    assert result.covered_business_rules == 1


@pytest.mark.governance
def test_p54_gate_passes_when_coverage_above_70_percent():
    """P5.4 should allow if at least 70% coverage."""

    session_state = {
        "BusinessRules": {
            "Rules": [
                {"id": "BR-1", "covered": True},
                {"id": "BR-2", "covered": True},
                {"id": "BR-3", "covered": True},
                {"id": "BR-4", "covered": False},
            ]
        }
    }
    result = evaluate_p54_business_rules_gate(session_state=session_state, phase_1_5_executed=True)
    assert result.status == "pending"


@pytest.mark.governance
def test_p56_gate_not_applicable_when_no_schema_or_contracts():
    """P5.6 is N/A if nothing touched that needs rollback."""

    session_state = {"TouchedSurface": {"SchemaPlanned": [], "ContractsPlanned": []}}
    result = evaluate_p56_rollback_safety_gate(session_state=session_state)
    assert result.status == "not-applicable"


@pytest.mark.governance
def test_p56_gate_blocks_when_rollback_strategy_missing():
    """P5.6 must block if schema touched but no rollback strategy."""

    session_state = {
        "TouchedSurface": {"SchemaPlanned": ["users_table"], "ContractsPlanned": []}
    }
    result = evaluate_p56_rollback_safety_gate(session_state=session_state)
    assert result.status == "rejected"
    assert result.reason_code == BLOCKED_P5_6_ROLLBACK_SAFETY_GATE
    assert result.schema_touched is True


@pytest.mark.governance
def test_p56_gate_pending_when_rollback_present():
    """P5.6 should allow if rollback strategy exists."""

    session_state = {
        "TouchedSurface": {"SchemaPlanned": ["users_table"], "ContractsPlanned": []},
        "RollbackStrategy": {"DataMigrationReversible": True},
    }
    result = evaluate_p56_rollback_safety_gate(session_state=session_state)
    assert result.status == "pending"
    assert result.rollback_strategy_present is True


@pytest.mark.governance
def test_p56_gate_blocks_when_migration_not_reversible_without_safety_steps():
    """P5.6 must block if migration not reversible and no safety steps."""

    session_state = {
        "TouchedSurface": {"SchemaPlanned": ["users_table"], "ContractsPlanned": []},
        "RollbackStrategy": {"DataMigrationReversible": False},
    }
    result = evaluate_p56_rollback_safety_gate(session_state=session_state)
    assert result.status == "rejected"
    assert result.rollback_reversible is False


@pytest.mark.governance
def test_p6_prerequisites_blocks_when_p5_not_approved():
    """P6 must block if P5-Architecture not approved."""

    session_state = {"Gates": {"P5-Architecture": "pending", "P5.3-TestQuality": "pass"}}
    result = evaluate_p6_prerequisites(
        session_state=session_state, phase_1_5_executed=False, rollback_safety_applies=False
    )
    assert result.passed is False
    assert result.reason_code == BLOCKED_P6_PREREQUISITES_NOT_MET
    assert result.p5_architecture_approved is False


@pytest.mark.governance
def test_p6_prerequisites_blocks_when_p53_not_passed():
    """P6 must block if P5.3 not passed."""

    session_state = {"Gates": {"P5-Architecture": "approved", "P5.3-TestQuality": "fail"}}
    result = evaluate_p6_prerequisites(
        session_state=session_state, phase_1_5_executed=False, rollback_safety_applies=False
    )
    assert result.passed is False
    assert result.p53_passed is False


@pytest.mark.governance
def test_p6_prerequisites_blocks_when_p54_not_compliant():
    """P6 must block if P5.4 not compliant when Phase 1.5 ran."""

    session_state = {
        "Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.4-BusinessRules": "gap-detected",
        }
    }
    result = evaluate_p6_prerequisites(
        session_state=session_state, phase_1_5_executed=True, rollback_safety_applies=False
    )
    assert result.passed is False
    assert result.p54_compliant is False


@pytest.mark.governance
def test_p6_prerequisites_blocks_when_p56_not_approved():
    """P6 must block if P5.6 not approved when rollback safety applies."""

    session_state = {
        "Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.6-RollbackSafety": "rejected",
        }
    }
    result = evaluate_p6_prerequisites(
        session_state=session_state, phase_1_5_executed=False, rollback_safety_applies=True
    )
    assert result.passed is False
    assert result.p56_approved is False


@pytest.mark.governance
def test_p6_prerequisites_passes_when_all_gates_satisfied():
    """P6 should pass when all prerequisite gates are satisfied."""

    session_state = {
        "Gates": {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.4-BusinessRules": "compliant",
            "P5.6-RollbackSafety": "approved",
        }
    }
    result = evaluate_p6_prerequisites(
        session_state=session_state, phase_1_5_executed=True, rollback_safety_applies=True
    )
    assert result.passed is True
    assert result.reason_code == REASON_CODE_NONE
