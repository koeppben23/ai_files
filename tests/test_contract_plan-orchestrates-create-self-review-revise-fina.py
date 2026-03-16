from governance.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action({"status": "OK", "phase": "5-ArchitectureReview", "active_gate": "Architecture Review Gate"})
    assert render.command == "/continue"


globals()["test_plan-orchestrates-create-self-review-revise-fina"] = _impl
