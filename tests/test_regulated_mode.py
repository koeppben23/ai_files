"""Tests for governance.domain.regulated_mode — Regulated mode state machine.

Covers: Happy / Edge / Corner / Bad paths.

Contract version under test: REGULATED_MODE.v1
"""

from __future__ import annotations

import pytest

from governance.domain.regulated_mode import (
    CONTRACT_VERSION,
    RegulatedModeState,
    RegulatedModeConstraint,
    RegulatedModeConfig,
    RegulatedModeEvaluation,
    DEFAULT_CONFIG,
    ACTIVE_CONSTRAINTS,
    INACTIVE_CONSTRAINTS,
    COMPLIANCE_FRAMEWORKS,
    evaluate_mode,
    get_minimum_retention_days,
    is_constraint_active,
    validate_retention_change,
    regulated_mode_summary,
)


# ===================================================================
# Happy path
# ===================================================================

class TestEvaluateModeHappy:
    """Happy: mode evaluation returns expected results."""

    def test_active_mode_is_active(self):
        config = RegulatedModeConfig(state=RegulatedModeState.ACTIVE)
        result = evaluate_mode(config)
        assert result.is_active is True
        assert result.state == RegulatedModeState.ACTIVE

    def test_active_mode_has_all_constraints(self):
        config = RegulatedModeConfig(state=RegulatedModeState.ACTIVE)
        result = evaluate_mode(config)
        assert len(result.active_constraints) == 7
        assert result.active_constraints == ACTIVE_CONSTRAINTS

    def test_inactive_mode_is_not_active(self):
        config = RegulatedModeConfig(state=RegulatedModeState.INACTIVE)
        result = evaluate_mode(config)
        assert result.is_active is False
        assert result.state == RegulatedModeState.INACTIVE

    def test_inactive_mode_has_no_constraints(self):
        config = RegulatedModeConfig(state=RegulatedModeState.INACTIVE)
        result = evaluate_mode(config)
        assert len(result.active_constraints) == 0

    def test_default_config_is_inactive(self):
        result = evaluate_mode(DEFAULT_CONFIG)
        assert result.is_active is False


class TestTransitioningModeHappy:
    """Happy: transitioning treated as active (fail-closed)."""

    def test_transitioning_is_active(self):
        config = RegulatedModeConfig(state=RegulatedModeState.TRANSITIONING)
        result = evaluate_mode(config)
        assert result.is_active is True

    def test_transitioning_has_all_constraints(self):
        config = RegulatedModeConfig(state=RegulatedModeState.TRANSITIONING)
        result = evaluate_mode(config)
        assert result.active_constraints == ACTIVE_CONSTRAINTS

    def test_transitioning_reason_mentions_fail_closed(self):
        config = RegulatedModeConfig(state=RegulatedModeState.TRANSITIONING)
        result = evaluate_mode(config)
        assert "fail-closed" in result.reason.lower()


class TestMinimumRetentionHappy:
    """Happy: compliance framework retention lookups."""

    def test_datev_is_10_years(self):
        assert get_minimum_retention_days("DATEV") == 3650

    def test_gobd_is_10_years(self):
        assert get_minimum_retention_days("GoBD") == 3650

    def test_bafin_is_5_years(self):
        assert get_minimum_retention_days("BaFin") == 1825

    def test_sox_is_7_years(self):
        assert get_minimum_retention_days("SOX") == 2555

    def test_default_fallback(self):
        assert get_minimum_retention_days("DEFAULT") == 365


class TestIsConstraintActiveHappy:
    """Happy: individual constraint checks."""

    def test_retention_locked_when_active(self):
        config = RegulatedModeConfig(state=RegulatedModeState.ACTIVE)
        assert is_constraint_active(config, RegulatedModeConstraint.RETENTION_LOCKED)

    def test_archive_immutable_when_active(self):
        config = RegulatedModeConfig(state=RegulatedModeState.ACTIVE)
        assert is_constraint_active(config, RegulatedModeConstraint.ARCHIVE_IMMUTABLE)

    def test_no_constraints_when_inactive(self):
        config = RegulatedModeConfig(state=RegulatedModeState.INACTIVE)
        for constraint in RegulatedModeConstraint:
            assert not is_constraint_active(config, constraint)


class TestValidateRetentionChangeHappy:
    """Happy: retention change validation."""

    def test_extension_allowed_in_regulated(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="DATEV",
            minimum_retention_days=3650,
        )
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=3650,
            requested_retention_days=5000,
        )
        assert allowed is True

    def test_same_value_allowed_in_regulated(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="DATEV",
            minimum_retention_days=3650,
        )
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=3650,
            requested_retention_days=3650,
        )
        assert allowed is True

    def test_any_change_allowed_when_inactive(self):
        config = RegulatedModeConfig(state=RegulatedModeState.INACTIVE)
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=3650,
            requested_retention_days=30,
        )
        assert allowed is True


class TestRegulatedModeSummaryHappy:
    """Happy: summary produces well-formed dict."""

    def test_summary_has_expected_keys(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            customer_id="CUST-001",
            compliance_framework="DATEV",
        )
        summary = regulated_mode_summary(config)
        assert summary["contract_version"] == CONTRACT_VERSION
        assert summary["state"] == "active"
        assert summary["is_active"] is True
        assert summary["customer_id"] == "CUST-001"
        assert summary["compliance_framework"] == "DATEV"
        assert isinstance(summary["active_constraints"], list)
        assert len(summary["active_constraints"]) == 7


# ===================================================================
# Edge cases
# ===================================================================

class TestValidateRetentionChangeEdge:
    """Edge: boundary conditions on retention changes."""

    def test_reduce_to_framework_minimum_exact_is_allowed(self):
        """Reducing to exactly the framework minimum should be allowed
        if it's not below current."""
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="BaFin",
            minimum_retention_days=1825,
        )
        allowed, _ = validate_retention_change(
            config=config,
            current_retention_days=1825,
            requested_retention_days=1825,
        )
        assert allowed is True

    def test_framework_minimum_overrides_config_minimum(self):
        """If framework minimum > config minimum, framework wins."""
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="DATEV",
            minimum_retention_days=365,  # config says 1 year
        )
        # DATEV requires 3650, so reducing to 1000 should fail
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=5000,
            requested_retention_days=1000,
        )
        assert allowed is False

    def test_config_minimum_overrides_framework_minimum(self):
        """If config minimum > framework minimum, config wins."""
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="GDPR",  # 365 days
            minimum_retention_days=3650,  # config says 10 years
        )
        # Config minimum is 3650, so reducing to 1000 should fail
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=5000,
            requested_retention_days=1000,
        )
        assert allowed is False


class TestGetMinimumRetentionEdge:
    """Edge: unknown frameworks fall back to DEFAULT."""

    def test_unknown_framework_returns_default(self):
        result = get_minimum_retention_days("UnknownFramework")
        assert result == COMPLIANCE_FRAMEWORKS["DEFAULT"]

    def test_empty_framework_returns_default(self):
        result = get_minimum_retention_days("")
        assert result == COMPLIANCE_FRAMEWORKS["DEFAULT"]


# ===================================================================
# Corner cases
# ===================================================================

class TestRegulatedModeCorner:
    """Corner: unusual but valid configurations."""

    def test_config_with_all_optional_fields(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            customer_id="CUST-999",
            compliance_framework="DATEV",
            activated_at="2025-01-01T00:00:00Z",
            activated_by="admin@company.de",
            minimum_retention_days=7300,
            export_format="zip",
            require_checksums_on_export=True,
        )
        result = evaluate_mode(config)
        assert result.is_active is True

    def test_config_with_zero_retention(self):
        """Zero retention is valid in config (framework overrides will apply)."""
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            minimum_retention_days=0,
            compliance_framework="DATEV",
        )
        result = evaluate_mode(config)
        assert result.is_active is True

    def test_all_constraints_have_unique_values(self):
        values = [c.value for c in RegulatedModeConstraint]
        assert len(values) == len(set(values))

    def test_all_states_have_unique_values(self):
        values = [s.value for s in RegulatedModeState]
        assert len(values) == len(set(values))

    def test_config_is_frozen(self):
        config = RegulatedModeConfig(state=RegulatedModeState.ACTIVE)
        with pytest.raises(AttributeError):
            config.state = RegulatedModeState.INACTIVE  # type: ignore[misc]

    def test_evaluation_is_frozen(self):
        config = RegulatedModeConfig(state=RegulatedModeState.ACTIVE)
        result = evaluate_mode(config)
        with pytest.raises(AttributeError):
            result.is_active = False  # type: ignore[misc]


# ===================================================================
# Bad paths
# ===================================================================

class TestValidateRetentionChangeBad:
    """Bad: attempts to shorten retention in regulated mode."""

    def test_shorten_below_framework_denied(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="DATEV",
            minimum_retention_days=3650,
        )
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=5000,
            requested_retention_days=100,
        )
        assert allowed is False
        assert "3650" in reason

    def test_shorten_below_current_denied(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="GDPR",
            minimum_retention_days=365,
        )
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=1000,
            requested_retention_days=500,
        )
        assert allowed is False

    def test_shorten_to_zero_denied(self):
        config = RegulatedModeConfig(
            state=RegulatedModeState.ACTIVE,
            compliance_framework="DATEV",
            minimum_retention_days=3650,
        )
        allowed, reason = validate_retention_change(
            config=config,
            current_retention_days=3650,
            requested_retention_days=0,
        )
        assert allowed is False


# ===================================================================
# Contract invariants
# ===================================================================

class TestRegulatedModeInvariants:
    """Contract-level invariants."""

    def test_contract_version(self):
        assert CONTRACT_VERSION == "REGULATED_MODE.v1"

    def test_active_constraints_count(self):
        assert len(ACTIVE_CONSTRAINTS) == 7

    def test_inactive_constraints_empty(self):
        assert len(INACTIVE_CONSTRAINTS) == 0

    def test_all_constraint_enums_in_active_set(self):
        """Every defined constraint should be in ACTIVE_CONSTRAINTS."""
        for constraint in RegulatedModeConstraint:
            assert constraint in ACTIVE_CONSTRAINTS

    def test_compliance_frameworks_all_positive(self):
        for name, days in COMPLIANCE_FRAMEWORKS.items():
            assert days > 0, f"Framework {name} has non-positive days: {days}"

    def test_default_framework_exists(self):
        assert "DEFAULT" in COMPLIANCE_FRAMEWORKS
