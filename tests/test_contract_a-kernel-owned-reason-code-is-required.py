from governance_runtime.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action({"status": "OK", "phase": "6-PostFlight", "active_gate": "Implementation Blocked"})
    assert render.command == "/implement"


globals()["test_a-kernel-owned-reason-code-is-required"] = _impl
