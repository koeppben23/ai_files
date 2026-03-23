from governance_runtime.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action(
        {"status": "OK", "phase": "5.4", "active_gate": "Business Rules Validation", "p54_evaluated_status": "compliant"}
    )
    assert render.command == "/continue"


globals()["test_materialize-the-official-phase-5-completion-stat"] = _impl
