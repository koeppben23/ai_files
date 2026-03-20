from governance_runtime.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action({"status": "BLOCKED", "phase": "6-PostFlight", "active_gate": "Implementation Blocked"})
    assert render.command == "/continue"
    assert "resolve the reported blocker evidence" in render.label


globals()["test_blockers-must-carry-a-canonical-reason-code"] = _impl
