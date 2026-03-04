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


def test_rulebook_gate_happy_path_phase4_with_full_evidence() -> None:
    """Phase >= 4 with core + profile + addons + active_profile + addons_evidence -> gate satisfied."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={
            "core": "loaded",
            "profile": "loaded",
            "addons": {"riskTiering": "rules.risk-tiering.yml"},
        },
        active_profile="profile.fallback-minimum",
        addons_evidence={"riskTiering": {"status": "loaded"}},
    )
    assert result.ok is True
    assert result.code == "OK"


# --- Edge / corner / bad-path tests for enhanced rulebook_gate ---

def test_rulebook_gate_blocks_phase4_missing_addons() -> None:
    """Phase >= 4 with core+profile but no addons -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={"core": "loaded", "profile": "loaded"},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_phase4_empty_addons() -> None:
    """Phase >= 4 with addons={} (empty dict) -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={"core": "loaded", "profile": "loaded", "addons": {}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_phase4_addons_all_blank() -> None:
    """Addons dict with only blank values -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={"core": "loaded", "profile": "loaded", "addons": {"foo": "", "bar": "  "}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_phase4_addons_non_string_values() -> None:
    """Addons dict with non-string values (ints/None) -> blocks."""
    result = rulebook_gate(
        target_phase="5.0",
        loaded_rulebooks={"core": "loaded", "profile": "loaded", "addons": {"a": 42, "b": None}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_phase4_missing_active_profile() -> None:
    """Phase >= 4 with good addons but no active_profile -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={
            "core": "loaded",
            "profile": "loaded",
            "addons": {"riskTiering": "rules.risk-tiering.yml"},
        },
        active_profile=None,
        addons_evidence={"riskTiering": {"status": "loaded"}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"
    assert "active profile" in result.reason


def test_rulebook_gate_blocks_phase4_empty_active_profile() -> None:
    """Phase >= 4 with blank active_profile -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={
            "core": "loaded",
            "profile": "loaded",
            "addons": {"riskTiering": "rules.risk-tiering.yml"},
        },
        active_profile="   ",
        addons_evidence={"riskTiering": {"status": "loaded"}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_phase4_missing_addons_evidence() -> None:
    """Phase >= 4 with good addons + active_profile but no evidence -> blocks."""
    result = rulebook_gate(
        target_phase="5.1",
        loaded_rulebooks={
            "core": "loaded",
            "profile": "loaded",
            "addons": {"riskTiering": "rules.risk-tiering.yml"},
        },
        active_profile="profile.fallback-minimum",
        addons_evidence=None,
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"
    assert "addon evidence" in result.reason


def test_rulebook_gate_blocks_phase4_empty_addons_evidence() -> None:
    """Phase >= 4 with addons_evidence={} (empty) -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={
            "core": "loaded",
            "profile": "loaded",
            "addons": {"riskTiering": "rules.risk-tiering.yml"},
        },
        active_profile="profile.fallback-minimum",
        addons_evidence={},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_happy_path_phase5() -> None:
    """Phase 5 with all evidence -> passes."""
    result = rulebook_gate(
        target_phase="5.2",
        loaded_rulebooks={
            "core": "core.md",
            "profile": "profile.yml",
            "addons": {"risk": "risk.yml", "extra": "extra.yml"},
        },
        active_profile="profile.production",
        addons_evidence={"risk": {"status": "loaded"}, "extra": {"status": "loaded"}},
    )
    assert result.ok is True
    assert result.code == "OK"


def test_rulebook_gate_below_phase4_ignores_all_fields() -> None:
    """Phase < 4 always passes regardless of what's supplied."""
    for phase in ("1.0", "2.1", "3.9", "0"):
        result = rulebook_gate(
            target_phase=phase,
            loaded_rulebooks={},
            active_profile=None,
            addons_evidence=None,
        )
        assert result.ok is True, f"Expected OK for phase {phase}"


def test_rulebook_gate_non_numeric_phase_treated_as_zero() -> None:
    """Non-numeric phase token treated as major_phase=0 -> below 4 -> passes."""
    result = rulebook_gate(target_phase="invalid", loaded_rulebooks={})
    assert result.ok is True


def test_rulebook_gate_non_dict_loaded_rulebooks() -> None:
    """Non-dict loaded_rulebooks for phase >= 4 -> blocks."""
    result = rulebook_gate(target_phase="4.0", loaded_rulebooks=None)  # type: ignore[arg-type]
    assert result.ok is False
    assert result.code == "RULEBOOKS_MISSING"


def test_rulebook_gate_blocks_missing_core() -> None:
    """Phase >= 4 with profile but no core -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={"profile": "loaded", "addons": {"r": "v"}},
        active_profile="p",
        addons_evidence={"r": {}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"


def test_rulebook_gate_blocks_missing_profile() -> None:
    """Phase >= 4 with core but no profile -> blocks."""
    result = rulebook_gate(
        target_phase="4.0",
        loaded_rulebooks={"core": "loaded", "addons": {"r": "v"}},
        active_profile="p",
        addons_evidence={"r": {}},
    )
    assert result.ok is False
    assert result.code == "RULEBOOKS_INCOMPLETE"
