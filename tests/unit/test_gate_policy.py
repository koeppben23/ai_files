from governance.domain.policies.gate_policy import persistence_gate, rulebook_gate


def test_persistence_gate_fail_closed_missing_flags() -> None:
    result = persistence_gate({})
    assert result.ok is False


def test_persistence_gate_happy_path() -> None:
    """Both flags true -> gate satisfied."""
    state = {
        "CommitFlags": {
            "PersistenceCommitted": True,
            "WorkspaceArtifactsCommitted": True,
        }
    }
    result = persistence_gate(state)
    assert result.ok is True
    assert result.code == "OK"


def test_rulebook_gate_blocks_phase4_without_core_profile() -> None:
    result = rulebook_gate(target_phase="4.0", loaded_rulebooks={})
    assert result.ok is False


def test_rulebook_gate_blocks_phase5_without_core_profile() -> None:
    result = rulebook_gate(target_phase="5.2", loaded_rulebooks={})
    assert result.ok is False


def test_rulebook_gate_blocks_when_anchor_missing_for_phase4_plus() -> None:
    result = rulebook_gate(
        target_phase="4.2",
        loaded_rulebooks={"core": "loaded", "profile": "loaded", "anchors_ok": False},
    )
    assert result.ok is False
    assert result.code == "RULEBOOK_ANCHOR_MISSING"


def test_rulebook_gate_not_required_below_phase4() -> None:
    """Phase < 4 -> gate not required (always OK)."""
    result = rulebook_gate(target_phase="3.0", loaded_rulebooks={})
    assert result.ok is True
    assert result.code == "OK"


def test_rulebook_gate_happy_path_phase4_with_core_and_profile() -> None:
    """Phase >= 4 with core + profile -> gate satisfied."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={"core": "loaded", "profile": "loaded"},
    )
    assert result.ok is True
    assert result.code == "OK"
