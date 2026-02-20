"""Tests for Phase 5 Review Configuration."""

from __future__ import annotations

import pytest

from governance.application.use_cases.phase5_review_config import (
    get_max_iterations,
    is_human_escalation_enabled,
    is_fail_fast_enabled,
    load_phase5_review_config,
    Phase5ReviewConfig,
    ReviewCriteria,
    ModeConfig,
    EscalationConfig,
)


@pytest.mark.governance
class TestLoadPhase5ReviewConfig:
    """Tests for config loading."""

    def test_loads_config_from_yaml(self):
        config = load_phase5_review_config(force_reload=True)
        assert config is not None
        assert isinstance(config, Phase5ReviewConfig)

    def test_config_has_default_max_iterations(self):
        config = load_phase5_review_config(force_reload=True)
        assert config.max_iterations == 3

    def test_config_has_criteria(self):
        config = load_phase5_review_config(force_reload=True)
        assert isinstance(config.criteria, ReviewCriteria)
        assert config.criteria.test_coverage_min_percent == 80

    def test_config_has_modes(self):
        config = load_phase5_review_config(force_reload=True)
        assert "user" in config.modes
        assert "pipeline" in config.modes
        assert "agents_strict" in config.modes


@pytest.mark.governance
class TestGetMaxIterations:
    """Tests for get_max_iterations helper."""

    def test_user_mode_max_iterations(self):
        max_iter = get_max_iterations("user")
        assert max_iter == 3

    def test_pipeline_mode_max_iterations(self):
        max_iter = get_max_iterations("pipeline")
        assert max_iter == 3

    def test_agents_strict_mode_max_iterations(self):
        max_iter = get_max_iterations("agents_strict")
        assert max_iter == 1


@pytest.mark.governance
class TestIsHumanEscalationEnabled:
    """Tests for is_human_escalation_enabled helper."""

    def test_user_mode_has_human_escalation(self):
        assert is_human_escalation_enabled("user") is True

    def test_pipeline_mode_no_human_escalation(self):
        assert is_human_escalation_enabled("pipeline") is False

    def test_agents_strict_mode_no_human_escalation(self):
        assert is_human_escalation_enabled("agents_strict") is False


@pytest.mark.governance
class TestIsFailFastEnabled:
    """Tests for is_fail_fast_enabled helper."""

    def test_user_mode_no_fail_fast(self):
        assert is_fail_fast_enabled("user") is False

    def test_pipeline_mode_has_fail_fast(self):
        assert is_fail_fast_enabled("pipeline") is True

    def test_agents_strict_mode_no_fail_fast(self):
        assert is_fail_fast_enabled("agents_strict") is False
