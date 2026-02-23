from governance.application.use_cases.route_phase import RoutePhaseInput, RoutePhaseService


def test_rulebook_gate_applies_to_target_phase_not_request() -> None:
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="4.1",
            loaded_rulebooks={"core": "x"},
            persistence_state={
                "CommitFlags": {
                    "PersistenceCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                }
            },
        )
    )
    assert routed.blocked_code == "RULEBOOKS_INCOMPLETE"
