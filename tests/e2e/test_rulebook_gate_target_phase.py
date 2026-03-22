from governance_runtime.application.use_cases.route_phase import RoutePhaseInput, RoutePhaseService


_FULL_PERSISTENCE = {
    "CommitFlags": {
        "PersistenceCommitted": True,
        "WorkspaceArtifactsCommitted": True,
    }
}

_FULL_RULEBOOKS = {
    "core": "${COMMANDS_HOME}/rules.md",
    "profile": "${PROFILES_HOME}/rules.fallback-minimum.yml",
    "addons": {"riskTiering": "${PROFILES_HOME}/rules.risk-tiering.yml"},
}


def test_rulebook_gate_applies_to_target_phase_not_request() -> None:
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="4.1",
            loaded_rulebooks={"core": "x"},
            persistence_state=_FULL_PERSISTENCE,
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
            persistence_state=_FULL_PERSISTENCE,
        )
    )
    assert routed.blocked_code == "RULEBOOK_ANCHOR_MISSING"


def test_rulebook_gate_blocks_phase4_without_addons_evidence() -> None:
    """Phase >= 4 with core+profile+addons but no active_profile/addons_evidence -> blocks."""
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="4.0",
            loaded_rulebooks=_FULL_RULEBOOKS,
            persistence_state=_FULL_PERSISTENCE,
            # active_profile and addons_evidence default to None
        )
    )
    assert routed.blocked_code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_phase5_missing_addons_evidence() -> None:
    """Phase 5 with active_profile but no addons_evidence -> blocks."""
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="5.0",
            loaded_rulebooks=_FULL_RULEBOOKS,
            persistence_state=_FULL_PERSISTENCE,
            active_profile="profile.fallback-minimum",
            addons_evidence=None,
        )
    )
    assert routed.blocked_code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_happy_path_phase4_full_evidence() -> None:
    """Phase >= 4 with complete evidence -> passes (no blocked_code)."""
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="4.1",
            loaded_rulebooks=_FULL_RULEBOOKS,
            persistence_state=_FULL_PERSISTENCE,
            active_profile="profile.fallback-minimum",
            addons_evidence={"riskTiering": {"status": "loaded"}},
        )
    )
    assert routed.blocked_code is None
    assert routed.reason == "ok"


def test_rulebook_gate_happy_path_phase5_full_evidence() -> None:
    """Phase 5 with complete evidence -> passes."""
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="5.2",
            loaded_rulebooks=_FULL_RULEBOOKS,
            persistence_state=_FULL_PERSISTENCE,
            active_profile="profile.production",
            addons_evidence={"riskTiering": {"status": "loaded"}},
        )
    )
    assert routed.blocked_code is None


def test_rulebook_gate_not_required_below_phase4() -> None:
    """Phase < 4 always passes regardless of rulebook state."""
    service = RoutePhaseService()
    routed = service.run(
        RoutePhaseInput(
            requested_phase="2.0",
            target_phase="3.0",
            loaded_rulebooks={},
            persistence_state=_FULL_PERSISTENCE,
        )
    )
    assert routed.blocked_code is None
