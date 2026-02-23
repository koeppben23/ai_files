from governance.application.use_cases.route_phase import RoutePhaseInput, RoutePhaseService, RoutedPhase


def test_routed_phase_shape() -> None:
    routed = RoutedPhase(phase="1.1-Bootstrap", blocked_code=None, reason="ok", next_action="continue")
    assert routed.phase == "1.1-Bootstrap"


def test_route_phase_applies_rulebook_gate_on_target_phase() -> None:
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="4.1",
            loaded_rulebooks={"core": "loaded"},
            persistence_state={
                "CommitFlags": {
                    "PersistenceCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                }
            },
        )
    )
    assert routed.blocked_code == "RULEBOOKS_INCOMPLETE"


def test_route_phase_blocks_when_persistence_not_committed() -> None:
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="3.0",
            target_phase=None,
            loaded_rulebooks={"core": "loaded", "profile": "loaded"},
            persistence_state={"CommitFlags": {"PersistenceCommitted": False, "WorkspaceArtifactsCommitted": False}},
        )
    )
    assert routed.blocked_code == "PERSISTENCE_NOT_COMMITTED"
