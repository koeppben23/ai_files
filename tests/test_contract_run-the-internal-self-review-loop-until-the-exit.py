from governance.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action(
        {"status": "OK", "phase": "6-PostFlight", "active_gate": "Implementation Internal Review"}
    )
    assert render.command == "/continue"


globals()["test_run-the-internal-self-review-loop-until-the-exit"] = _impl
