from governance.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action({"status": "OK", "phase": "4", "active_gate": "Ticket Input Gate"})
    assert render.command == "/ticket"
    assert "/review" in render.label


globals()["test_free-text-is-evidence-only-not-the-primary-signa"] = _impl
