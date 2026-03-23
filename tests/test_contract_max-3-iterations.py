from governance_runtime.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action(
        {"status": "OK", "phase": "6-PostFlight", "active_gate": "Implementation Internal Review", "phase6_review_iterations": 3}
    )
    assert render.command == "/continue"


globals()["test_max-3-iterations"] = _impl
