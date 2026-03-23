from governance_runtime.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    ok_render = resolve_next_action({"status": "OK", "phase": "5-ArchitectureReview", "active_gate": "Architecture Review Gate"})
    blocked_render = resolve_next_action({"status": "BLOCKED", "phase": "5-ArchitectureReview", "active_gate": "Architecture Review Gate"})
    assert ok_render.command == "/continue"
    assert blocked_render.label.startswith("resolve the reported blocker evidence")


globals()["test_plan-returns-a-final-plan-or-a-real-blocker-with"] = _impl
