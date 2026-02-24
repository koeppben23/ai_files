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


def test_rulebook_anchor_missing_blocks_target_phase_four_plus() -> None:
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="5.0",
            loaded_rulebooks={"core": "loaded", "profile": "loaded", "anchors_ok": False},
            persistence_state={
                "CommitFlags": {
                    "PersistenceCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                }
            },
        )
    )
    assert routed.blocked_code == "RULEBOOK_ANCHOR_MISSING"
