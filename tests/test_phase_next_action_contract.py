from __future__ import annotations

from governance.engine.phase_next_action_contract import validate_phase_next_action_contract


def test_phase_contract_rejects_ticket_prompt_before_phase4():
    errors = validate_phase_next_action_contract(
        status="degraded",
        session_state={"phase": "2.1-DecisionPack"},
        next_text="Provide the ticket/goal and scope to plan",
        why_text="Phase 4 requires concrete task",
    )
    assert "next_action must not request task/ticket input before phase 4" in errors


def test_phase_contract_accepts_phase15_after_phase21():
    errors = validate_phase_next_action_contract(
        status="normal",
        session_state={
            "phase": "1.5-BusinessRules",
            "previous_phase": "2.1-DecisionPack",
            "next_gate_condition": "Proceed to Phase 3A",
        },
        next_text="Proceed to Phase 3A API inventory",
        why_text="Phase 1.5 completed after decision pack",
    )
    assert errors == ()
