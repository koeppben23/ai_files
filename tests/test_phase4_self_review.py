"""Tests for Phase 4 Self-Review Mechanism."""

from __future__ import annotations

import pytest

from governance.application.use_cases.phase4_self_review import (
    RigorLevel,
    ReviewFinding,
    SelfReviewRound,
    SelfReviewState,
    SelfReviewConfig,
    ComplexitySignals,
    PolicyConfigError,
    create_self_review_state,
    record_review_round,
    get_focus_area,
    format_review_summary,
    load_self_review_config,
    classify_complexity_from_signals,
    check_pipeline_constraints,
    PIPELINE_BLOCK_REASONS,
)


@pytest.mark.governance
class TestReviewFinding:
    """Tests for ReviewFinding."""

    def test_critical_is_blocking(self):
        finding = ReviewFinding(
            category="security_vulnerability",
            severity="critical",
            message="SQL injection risk",
        )
        assert finding.is_blocking is True

    def test_warning_is_not_blocking(self):
        finding = ReviewFinding(
            category="style",
            severity="warning",
            message="Missing docstring",
        )
        assert finding.is_blocking is False

    def test_to_dict(self):
        finding = ReviewFinding(
            category="security",
            severity="critical",
            message="Test",
            location="file.py:10",
        )
        d = finding.to_dict()
        assert d["category"] == "security"
        assert d["severity"] == "critical"
        assert d["location"] == "file.py:10"


@pytest.mark.governance
class TestSelfReviewRound:
    """Tests for SelfReviewRound."""

    def test_has_blocking_when_critical(self):
        findings = (
            ReviewFinding(category="sec", severity="critical", message="X"),
        )
        round_obj = SelfReviewRound(
            round_index=1,
            focus="correctness",
            findings=findings,
            blocking_findings=findings,
            status="fail",
        )
        assert round_obj.has_blocking is True
        assert round_obj.has_critical is True

    def test_no_blocking_when_only_warnings(self):
        findings = (
            ReviewFinding(category="style", severity="warning", message="X"),
        )
        round_obj = SelfReviewRound(
            round_index=1,
            focus="correctness",
            findings=findings,
            blocking_findings=(),
            status="pass-with-notes",
        )
        assert round_obj.has_blocking is False
        assert round_obj.has_critical is False


@pytest.mark.governance
class TestCreateSelfReviewState:
    """Tests for state creation based on complexity."""

    def test_simple_crud_uses_minimal_rigor(self):
        state = create_self_review_state("SIMPLE-CRUD")
        assert state.rigor_level == "minimal"
        assert state.total_rounds == 1

    def test_complex_uses_maximum_rigor(self):
        state = create_self_review_state("COMPLEX")
        assert state.rigor_level == "maximum"
        assert state.total_rounds == 3

    def test_standard_uses_standard_rigor(self):
        state = create_self_review_state("STANDARD")
        assert state.rigor_level == "standard"
        assert state.total_rounds == 3

    def test_operating_mode_affects_max_cycles(self):
        state_user = create_self_review_state("STANDARD", operating_mode="user")
        state_pipeline = create_self_review_state("STANDARD", operating_mode="pipeline")
        state_strict = create_self_review_state("STANDARD", operating_mode="agents_strict")
        
        assert state_user.max_cycles == 2
        assert state_pipeline.max_cycles == 2
        assert state_strict.max_cycles == 1


@pytest.mark.governance
class TestRecordReviewRound:
    """Tests for recording review rounds."""

    def test_first_round_increments_count(self):
        state = create_self_review_state("STANDARD")
        new_state = record_review_round(
            state,
            focus="correctness",
            findings=[],
        )
        assert new_state.rounds_completed == 1
        assert len(new_state.rounds) == 1

    def test_pass_status_when_no_findings(self):
        state = create_self_review_state("STANDARD")
        new_state = record_review_round(
            state,
            focus="correctness",
            findings=[],
        )
        assert new_state.rounds[0].status == "pass"

    def test_fail_status_when_blocking(self):
        state = create_self_review_state("STANDARD")
        finding = ReviewFinding(
            category="security_vulnerability",
            severity="critical",
            message="XSS risk",
        )
        new_state = record_review_round(
            state,
            focus="correctness",
            findings=[finding],
        )
        assert new_state.rounds[0].status == "fail"
        assert len(new_state.rounds[0].blocking_findings) == 1

    def test_second_pass_triggered_on_critical_at_end(self):
        state = create_self_review_state("STANDARD")
        
        # Round 1
        state = record_review_round(state, focus="correctness", findings=[])
        # Round 2
        state = record_review_round(state, focus="completeness", findings=[])
        # Round 3 with critical
        finding = ReviewFinding(
            category="security_vulnerability",
            severity="critical",
            message="Critical issue",
        )
        state = record_review_round(state, focus="robustness", findings=[finding])
        
        assert state.critical_triggered_second_pass is True
        assert state.final_status == "second-pass-triggered"
        assert state.current_cycle == 2
        assert state.rounds_completed == 0  # Reset for second pass

    def test_no_second_pass_in_agents_strict(self):
        state = create_self_review_state("STANDARD", operating_mode="agents_strict")
        
        # Complete all rounds with critical
        for i in range(3):
            finding = ReviewFinding(
                category="security_vulnerability",
                severity="critical",
                message=f"Issue {i}",
            )
            state = record_review_round(state, focus=f"focus-{i}", findings=[finding])
        
        # agents_strict has max_cycles=1, so no second pass
        assert state.current_cycle == 1


@pytest.mark.governance
class TestGetFocusArea:
    """Tests for focus area selection."""

    def test_minimal_has_correctness_only(self):
        state = create_self_review_state("SIMPLE-CRUD")
        assert get_focus_area(state) == "correctness"

    def test_standard_has_three_focus_areas(self):
        state = create_self_review_state("STANDARD")
        assert get_focus_area(state) == "correctness"
        
        state = record_review_round(state, focus="correctness", findings=[])
        assert get_focus_area(state) == "completeness"
        
        state = record_review_round(state, focus="completeness", findings=[])
        assert get_focus_area(state) == "robustness"

    def test_maximum_has_five_focus_areas(self):
        state = create_self_review_state("COMPLEX")
        
        expected = ["correctness", "completeness", "robustness", "security", "production-readiness"]
        for i, expected_focus in enumerate(expected):
            assert get_focus_area(state) == expected_focus
            state = record_review_round(state, focus=expected_focus, findings=[])


@pytest.mark.governance
class TestStateSerialization:
    """Tests for state serialization."""

    def test_to_dict_contains_required_fields(self):
        state = create_self_review_state("STANDARD")
        state = record_review_round(
            state,
            focus="correctness",
            findings=[ReviewFinding(category="test", severity="warning", message="X")],
        )
        
        d = state.to_dict()
        
        assert "complexity_class" in d
        assert "rigor_level" in d
        assert "operating_mode" in d
        assert "rounds" in d
        assert "rounds_completed" in d
        assert "total_rounds" in d
        assert "final_status" in d

    def test_round_to_dict(self):
        state = create_self_review_state("STANDARD")
        state = record_review_round(state, focus="correctness", findings=[])
        
        round_dict = state.rounds[0].to_dict()
        
        assert round_dict["round_index"] == 1
        assert round_dict["focus"] == "correctness"
        assert round_dict["status"] == "pass"


@pytest.mark.governance
class TestDeterministicComplexityClassification:
    """Tests for deterministic complexity classification from signals."""

    def test_small_change_is_simple_crud(self):
        signals = ComplexitySignals(
            files_changed=2,
            loc_changed=50,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "SIMPLE-CRUD"

    def test_public_api_change_is_complex(self):
        signals = ComplexitySignals(
            files_changed=1,
            loc_changed=10,
            public_api_changed=True,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "COMPLEX"

    def test_schema_migration_is_complex(self):
        signals = ComplexitySignals(
            files_changed=1,
            schema_migration=True,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "COMPLEX"

    def test_security_paths_touched_is_complex(self):
        signals = ComplexitySignals(
            files_changed=1,
            security_paths_touched=True,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "COMPLEX"

    def test_large_change_is_complex(self):
        signals = ComplexitySignals(
            files_changed=15,
            loc_changed=800,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "COMPLEX"

    def test_moderate_change_is_standard(self):
        signals = ComplexitySignals(
            files_changed=5,
            loc_changed=200,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "STANDARD"

    def test_coverage_drop_is_complex(self):
        signals = ComplexitySignals(
            files_changed=3,
            test_coverage_delta=-10.0,
        )
        complexity = classify_complexity_from_signals(signals)
        assert complexity == "COMPLEX"


@pytest.mark.governance
class TestPipelineHardBlocks:
    """Tests for pipeline mode hard constraints."""

    def test_user_mode_allows_human_assist(self):
        blocked, reason = check_pipeline_constraints(
            operating_mode="user",
            requires_human_assist=True,
        )
        assert blocked is False
        assert reason == ""

    def test_pipeline_mode_blocks_human_assist(self):
        blocked, reason = check_pipeline_constraints(
            operating_mode="pipeline",
            requires_human_assist=True,
        )
        assert blocked is True
        assert reason == PIPELINE_BLOCK_REASONS["human_assist_required"]

    def test_pipeline_mode_blocks_interactive_prompt(self):
        blocked, reason = check_pipeline_constraints(
            operating_mode="pipeline",
            requires_interactive_prompt=True,
        )
        assert blocked is True
        assert reason == PIPELINE_BLOCK_REASONS["interactive_prompt_required"]

    def test_pipeline_mode_allows_internal_review(self):
        """Pipeline allows internal self-review rounds (no prompts)."""
        blocked, reason = check_pipeline_constraints(
            operating_mode="pipeline",
            requires_human_assist=False,
            requires_interactive_prompt=False,
        )
        assert blocked is False
        assert reason == ""

    def test_agents_strict_allows_internal_review(self):
        blocked, reason = check_pipeline_constraints(
            operating_mode="agents_strict",
            requires_human_assist=False,
            requires_interactive_prompt=False,
        )
        assert blocked is False


@pytest.mark.governance
class TestPolicyBoundConfigLoading:
    """Tests for policy-bound config fail-closed behavior."""

    def test_missing_config_raises_policy_error(self, tmp_path, monkeypatch):
        """When policy-bound config is missing, raise PolicyConfigError."""
        from governance.application.use_cases import phase4_self_review
        
        # Mock the repo-local path to non-existent location
        def fake_repo_local_path():
            return tmp_path / "nonexistent" / "config.yaml"
        
        monkeypatch.setattr(
            phase4_self_review,
            "_get_repo_local_config_path",
            fake_repo_local_path
        )
        phase4_self_review._CONFIG_CACHE = None  # Clear cache
        phase4_self_review._default_resolver = None  # No resolver configured
        
        with pytest.raises(phase4_self_review.PolicyConfigError) as exc_info:
            phase4_self_review.load_self_review_config(force_reload=True)
        
        assert "BLOCKED-ENGINE-SELFCHECK" in str(exc_info.value)

    def test_config_without_pack_locked_raises_error(self, tmp_path, monkeypatch):
        """Config must have pack_locked=true."""
        from governance.application.use_cases import phase4_self_review
        
        config_content = """
policy:
  precedence_level: "engine_master_policy"
  pack_locked: false
rigor_levels:
  standard:
    rounds: 3
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_content)
        
        def fake_repo_local_path():
            return config_path
        
        monkeypatch.setattr(
            phase4_self_review,
            "_get_repo_local_config_path",
            fake_repo_local_path
        )
        phase4_self_review._CONFIG_CACHE = None
        
        # Create a test resolver that allows repo-local fallback
        class TestResolver:
            def resolve_config_path(self):
                return None  # No canonical path
            def allow_repo_local_fallback(self):
                return True  # Allow repo-local for tests
        
        phase4_self_review.set_config_path_resolver(TestResolver())
        
        with pytest.raises(phase4_self_review.PolicyConfigError) as exc_info:
            phase4_self_review.load_self_review_config(force_reload=True)
        
        assert "pack_locked" in str(exc_info.value)

    def test_config_with_wrong_precedence_raises_error(self, tmp_path, monkeypatch):
        """Config must have correct precedence_level."""
        from governance.application.use_cases import phase4_self_review
        
        config_content = """
policy:
  precedence_level: "user_policy"
  pack_locked: true
rigor_levels:
  standard:
    rounds: 3
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_content)
        
        def fake_repo_local_path():
            return config_path
        
        monkeypatch.setattr(
            phase4_self_review,
            "_get_repo_local_config_path",
            fake_repo_local_path
        )
        phase4_self_review._CONFIG_CACHE = None
        
        # Create a test resolver that allows repo-local fallback
        class TestResolver:
            def resolve_config_path(self):
                return None  # No canonical path
            def allow_repo_local_fallback(self):
                return True  # Allow repo-local for tests
        
        phase4_self_review.set_config_path_resolver(TestResolver())
        
        with pytest.raises(phase4_self_review.PolicyConfigError) as exc_info:
            phase4_self_review.load_self_review_config(force_reload=True)
        
        assert "precedence_level" in str(exc_info.value)

    def test_valid_config_loads_successfully(self, tmp_path, monkeypatch):
        """Valid policy-bound config loads without error."""
        from governance.application.use_cases import phase4_self_review
        
        config_content = """
policy:
  version: "1.0.0"
  precedence_level: "engine_master_policy"
  pack_locked: true
  audit_on_change: "POLICY_PRECEDENCE_APPLIED"

rigor_levels:
  minimal:
    rounds: 1
    second_pass_on_critical: false
  standard:
    rounds: 3
    second_pass_on_critical: true

modes:
  user:
    max_cycles: 2
  pipeline:
    max_cycles: 2
    human_assist_allowed: false
    prompt_budget_check: "hard"
  agents_strict:
    max_cycles: 1

complexity_mapping:
  SIMPLE-CRUD: minimal
  STANDARD: standard
  COMPLEX: maximum

complexity_signals: {}
critical_issue_types:
  - security_vulnerability
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_content)
        
        def fake_repo_local_path():
            return config_path
        
        monkeypatch.setattr(
            phase4_self_review,
            "_get_repo_local_config_path",
            fake_repo_local_path
        )
        phase4_self_review._CONFIG_CACHE = None
        
        # Create a test resolver that allows repo-local fallback
        class TestResolver:
            def resolve_config_path(self):
                return None  # No canonical path
            def allow_repo_local_fallback(self):
                return True  # Allow repo-local for tests
        
        phase4_self_review.set_config_path_resolver(TestResolver())
        
        config = phase4_self_review.load_self_review_config(force_reload=True)
        
        assert config.rounds_for_rigor["minimal"] == 1
        assert config.rounds_for_rigor["standard"] == 3
        assert config.pipeline_human_assist_allowed is False
