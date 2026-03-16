from governance.engine.next_action_resolver import resolve_next_action


def _impl() -> None:
    render = resolve_next_action(
        {
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "active_gate": "Plan Record Preparation Gate",
            "plan_record_versions": 0,
        }
    )
    assert render.command == "/plan"


globals()["test_persist-plan-record-vn"] = _impl
