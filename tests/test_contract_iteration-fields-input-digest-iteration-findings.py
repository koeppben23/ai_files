from governance_runtime.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action(
        {"status": "OK", "phase": "6-PostFlight", "active_gate": "Implementation Internal Review", "phase6_review_iterations": 1}
    )
    assert render.command == "/continue"


globals()["test_iteration-fields-input-digest-iteration-findings"] = _impl
