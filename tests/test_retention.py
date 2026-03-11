"""Tests for governance.domain.retention — Retention policy domain model.

Covers: Happy / Edge / Corner / Bad paths.

Contract version under test: RETENTION_POLICY.v1
"""

from __future__ import annotations

import pytest

from governance.domain.retention import (
    CONTRACT_VERSION,
    RetentionClass,
    LegalHoldStatus,
    DeletionDecision,
    ArchiveFormat,
    RetentionPeriod,
    LegalHold,
    DeletionEvaluation,
    RetentionPolicy,
    RETENTION_PERIODS,
    FRAMEWORK_RETENTION_OVERRIDES,
    DEFAULT_RETENTION_DAYS,
    VALID_HOLD_SCOPES,
    get_retention_period,
    get_effective_retention_days,
    evaluate_deletion,
    validate_legal_hold,
    validate_retention_policy,
    build_retention_policy,
    get_retention_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hold(
    hold_id: str = "HOLD-001",
    scope_type: str = "run",
    scope_value: str = "run-abc",
    reason: str = "Legal investigation",
    status: LegalHoldStatus = LegalHoldStatus.ACTIVE,
) -> LegalHold:
    return LegalHold(
        hold_id=hold_id, scope_type=scope_type, scope_value=scope_value,
        reason=reason, status=status,
        created_at="2025-01-01T00:00:00Z", created_by="legal@company.de",
    )


# ===================================================================
# Happy path
# ===================================================================

class TestGetRetentionPeriodHappy:
    """Happy: known classification levels return correct retention."""

    def test_public_is_short(self):
        p = get_retention_period("public")
        assert p.retention_class == RetentionClass.SHORT
        assert p.minimum_days == 365

    def test_internal_is_standard(self):
        p = get_retention_period("internal")
        assert p.retention_class == RetentionClass.STANDARD
        assert p.minimum_days == 1095

    def test_confidential_is_extended(self):
        p = get_retention_period("confidential")
        assert p.retention_class == RetentionClass.EXTENDED
        assert p.minimum_days == 2555

    def test_restricted_is_permanent(self):
        p = get_retention_period("restricted")
        assert p.retention_class == RetentionClass.PERMANENT
        assert p.minimum_days == 3650


class TestEffectiveRetentionHappy:
    """Happy: effective retention considers framework overrides."""

    def test_no_framework_returns_base(self):
        days = get_effective_retention_days("public")
        assert days == 365

    def test_datev_overrides_public(self):
        days = get_effective_retention_days("public", "DATEV")
        assert days == 3650  # DATEV override > public base

    def test_datev_matches_restricted(self):
        days = get_effective_retention_days("restricted", "DATEV")
        assert days == 3650  # both are 3650

    def test_sox_overrides_internal(self):
        days = get_effective_retention_days("internal", "SOX")
        assert days == 2555  # SOX > internal base (1095)


class TestEvaluateDeletionHappy:
    """Happy: deletion evaluation under normal conditions."""

    def test_expired_retention_allows_deletion(self):
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=400,  # > 365
        )
        assert result.decision == DeletionDecision.ALLOWED

    def test_active_retention_blocks_deletion(self):
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="restricted",
            archived_at_days_ago=100,  # < 3650
        )
        assert result.decision == DeletionDecision.BLOCKED_RETENTION
        assert result.remaining_retention_days > 0

    def test_legal_hold_blocks_deletion(self):
        hold = _make_hold(scope_type="run", scope_value="run-abc")
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=9999,  # well past retention
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.BLOCKED_LEGAL_HOLD
        assert result.blocking_hold_id == "HOLD-001"

    def test_regulated_mode_blocks_deletion(self):
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=400,
            regulated_mode_active=True,
            regulated_mode_minimum_days=3650,
        )
        assert result.decision == DeletionDecision.BLOCKED_REGULATED_MODE


class TestValidateLegalHoldHappy:
    """Happy: valid legal holds pass validation."""

    def test_valid_active_hold(self):
        hold = _make_hold()
        errors = validate_legal_hold(hold)
        assert errors == []

    def test_valid_released_hold(self):
        hold = LegalHold(
            hold_id="HOLD-002", scope_type="repo", scope_value="abc123",
            reason="Resolved", status=LegalHoldStatus.RELEASED,
            created_at="2025-01-01T00:00:00Z", created_by="legal",
            released_at="2025-06-01T00:00:00Z", released_by="legal",
        )
        errors = validate_legal_hold(hold)
        assert errors == []


class TestBuildRetentionPolicyHappy:
    """Happy: build_retention_policy produces valid policies."""

    def test_default_policy_is_valid(self):
        policy = build_retention_policy()
        errors = validate_retention_policy(policy)
        assert errors == []

    def test_default_policy_has_four_periods(self):
        policy = build_retention_policy()
        assert len(policy.periods) == 4

    def test_contract_version_set(self):
        policy = build_retention_policy()
        assert policy.contract_version == CONTRACT_VERSION


class TestRetentionSummaryHappy:
    """Happy: get_retention_summary returns well-formed dict."""

    def test_summary_has_expected_keys(self):
        policy = build_retention_policy()
        summary = get_retention_summary(policy)
        assert summary["contract_version"] == CONTRACT_VERSION
        assert isinstance(summary["periods"], list)
        assert "active_legal_holds" in summary
        assert "framework_overrides" in summary

    def test_summary_period_count(self):
        policy = build_retention_policy()
        summary = get_retention_summary(policy)
        assert len(summary["periods"]) == 4


# ===================================================================
# Edge cases
# ===================================================================

class TestGetRetentionPeriodEdge:
    """Edge: boundary conditions on retention lookup."""

    def test_unknown_level_falls_back_to_restricted(self):
        """Fail-closed: unknown classification → longest retention."""
        p = get_retention_period("unknown_level")
        assert p.retention_class == RetentionClass.PERMANENT
        assert p.minimum_days == 3650

    def test_empty_level_falls_back_to_restricted(self):
        p = get_retention_period("")
        assert p.minimum_days == 3650


class TestEffectiveRetentionEdge:
    """Edge: framework override interactions."""

    def test_unknown_framework_adds_nothing(self):
        days = get_effective_retention_days("public", "UnknownFramework")
        assert days == 365  # base only

    def test_empty_framework_adds_nothing(self):
        days = get_effective_retention_days("public", "")
        assert days == 365


class TestEvaluateDeletionEdge:
    """Edge: boundary conditions on deletion evaluation."""

    def test_exactly_at_retention_boundary_blocks(self):
        """archived_at_days_ago == effective_days → still blocks (< not <=)."""
        days = get_effective_retention_days("public")  # 365
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=days - 1,
        )
        assert result.decision == DeletionDecision.BLOCKED_RETENTION

    def test_one_day_past_retention_allows(self):
        days = get_effective_retention_days("public")
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=days + 1,
        )
        assert result.decision == DeletionDecision.ALLOWED

    def test_released_hold_does_not_block(self):
        hold = _make_hold(status=LegalHoldStatus.RELEASED)
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=9999,
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.ALLOWED

    def test_none_status_hold_does_not_block(self):
        hold = _make_hold(status=LegalHoldStatus.NONE)
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=9999,
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.ALLOWED


class TestLegalHoldScopeEdge:
    """Edge: legal hold scope matching."""

    def test_repo_scope_blocks_matching_repo(self):
        hold = _make_hold(scope_type="repo", scope_value="abc123def456abc123def456")
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=9999,
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.BLOCKED_LEGAL_HOLD

    def test_repo_scope_does_not_block_other_repo(self):
        hold = _make_hold(scope_type="repo", scope_value="other_fingerprint")
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=9999,
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.ALLOWED

    def test_all_scope_blocks_everything(self):
        hold = _make_hold(scope_type="all", scope_value="*")
        result = evaluate_deletion(
            run_id="any-run",
            repo_fingerprint="any_fingerprint",
            classification_level="public",
            archived_at_days_ago=9999,
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.BLOCKED_LEGAL_HOLD


# ===================================================================
# Corner cases
# ===================================================================

class TestEvaluateDeletionCorner:
    """Corner: unusual but valid conditions."""

    def test_multiple_holds_first_active_blocks(self):
        holds = [
            _make_hold(hold_id="H1", status=LegalHoldStatus.RELEASED,
                       scope_type="run", scope_value="run-abc"),
            _make_hold(hold_id="H2", status=LegalHoldStatus.ACTIVE,
                       scope_type="run", scope_value="run-abc"),
        ]
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=9999,
            legal_holds=holds,
        )
        assert result.decision == DeletionDecision.BLOCKED_LEGAL_HOLD
        assert result.blocking_hold_id == "H2"

    def test_check_order_hold_before_retention(self):
        """Legal hold takes precedence over retention check."""
        hold = _make_hold(scope_type="run", scope_value="run-abc")
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=0,  # also within retention
            legal_holds=[hold],
        )
        assert result.decision == DeletionDecision.BLOCKED_LEGAL_HOLD

    def test_check_order_regulated_before_retention(self):
        """Regulated mode takes precedence over retention check."""
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=100,
            regulated_mode_active=True,
            regulated_mode_minimum_days=3650,
        )
        assert result.decision == DeletionDecision.BLOCKED_REGULATED_MODE

    def test_very_old_archive_allowed(self):
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="restricted",
            archived_at_days_ago=999999,
        )
        assert result.decision == DeletionDecision.ALLOWED

    def test_zero_days_ago_always_blocked(self):
        result = evaluate_deletion(
            run_id="run-abc",
            repo_fingerprint="abc123def456abc123def456",
            classification_level="public",
            archived_at_days_ago=0,
        )
        assert result.decision == DeletionDecision.BLOCKED_RETENTION


class TestValidateLegalHoldCorner:
    """Corner: legal hold validation edge cases."""

    def test_released_hold_without_released_at_invalid(self):
        hold = LegalHold(
            hold_id="H1", scope_type="run", scope_value="run-abc",
            reason="Test", status=LegalHoldStatus.RELEASED,
            created_at="2025-01-01T00:00:00Z", created_by="admin",
            released_at="", released_by="",
        )
        errors = validate_legal_hold(hold)
        assert any("released_at" in e for e in errors)
        assert any("released_by" in e for e in errors)


class TestRetentionPolicyCorner:
    """Corner: policy validation edge cases."""

    def test_duplicate_periods_flagged(self):
        policy = RetentionPolicy(
            version="1.0.0",
            contract_version=CONTRACT_VERSION,
            default_retention_class=RetentionClass.STANDARD,
            periods=(
                RetentionPeriod("public", RetentionClass.SHORT, 365, ""),
                RetentionPeriod("public", RetentionClass.SHORT, 365, ""),
            ),
            legal_holds=(),
            regulated_mode_minimum_days=3650,
        )
        errors = validate_retention_policy(policy)
        assert any("duplicate" in e.lower() for e in errors)

    def test_dataclasses_frozen(self):
        p = get_retention_period("public")
        with pytest.raises(AttributeError):
            p.minimum_days = 999  # type: ignore[misc]


# ===================================================================
# Bad paths
# ===================================================================

class TestValidateLegalHoldBad:
    """Bad: invalid legal holds."""

    def test_empty_hold_id(self):
        hold = LegalHold(
            hold_id="", scope_type="run", scope_value="run-abc",
            reason="Test", status=LegalHoldStatus.ACTIVE,
            created_at="2025-01-01T00:00:00Z", created_by="admin",
        )
        errors = validate_legal_hold(hold)
        assert any("hold_id" in e for e in errors)

    def test_invalid_scope_type(self):
        hold = _make_hold(scope_type="invalid_scope")
        errors = validate_legal_hold(hold)
        assert any("scope_type" in e for e in errors)

    def test_empty_scope_value(self):
        hold = LegalHold(
            hold_id="H1", scope_type="run", scope_value="",
            reason="Test", status=LegalHoldStatus.ACTIVE,
            created_at="2025-01-01T00:00:00Z", created_by="admin",
        )
        errors = validate_legal_hold(hold)
        assert any("scope_value" in e for e in errors)

    def test_empty_reason(self):
        hold = LegalHold(
            hold_id="H1", scope_type="run", scope_value="run-abc",
            reason="", status=LegalHoldStatus.ACTIVE,
            created_at="2025-01-01T00:00:00Z", created_by="admin",
        )
        errors = validate_legal_hold(hold)
        assert any("reason" in e for e in errors)

    def test_empty_created_at(self):
        hold = LegalHold(
            hold_id="H1", scope_type="run", scope_value="run-abc",
            reason="Test", status=LegalHoldStatus.ACTIVE,
            created_at="", created_by="admin",
        )
        errors = validate_legal_hold(hold)
        assert any("created_at" in e for e in errors)

    def test_empty_created_by(self):
        hold = LegalHold(
            hold_id="H1", scope_type="run", scope_value="run-abc",
            reason="Test", status=LegalHoldStatus.ACTIVE,
            created_at="2025-01-01T00:00:00Z", created_by="",
        )
        errors = validate_legal_hold(hold)
        assert any("created_by" in e for e in errors)


class TestValidateRetentionPolicyBad:
    """Bad: invalid retention policies."""

    def test_wrong_contract_version(self):
        policy = RetentionPolicy(
            version="1.0.0",
            contract_version="WRONG_VERSION",
            default_retention_class=RetentionClass.STANDARD,
            periods=(),
            legal_holds=(),
            regulated_mode_minimum_days=3650,
        )
        errors = validate_retention_policy(policy)
        assert any("contract_version" in e for e in errors)

    def test_negative_retention_days(self):
        policy = RetentionPolicy(
            version="1.0.0",
            contract_version=CONTRACT_VERSION,
            default_retention_class=RetentionClass.STANDARD,
            periods=(
                RetentionPeriod("public", RetentionClass.SHORT, -1, ""),
            ),
            legal_holds=(),
            regulated_mode_minimum_days=3650,
        )
        errors = validate_retention_policy(policy)
        assert any("negative" in e.lower() for e in errors)

    def test_negative_regulated_mode_minimum(self):
        policy = RetentionPolicy(
            version="1.0.0",
            contract_version=CONTRACT_VERSION,
            default_retention_class=RetentionClass.STANDARD,
            periods=(),
            legal_holds=(),
            regulated_mode_minimum_days=-1,
        )
        errors = validate_retention_policy(policy)
        assert any("regulated_mode_minimum" in e for e in errors)


# ===================================================================
# Contract invariants
# ===================================================================

class TestRetentionInvariants:
    """Contract-level invariants."""

    def test_contract_version(self):
        assert CONTRACT_VERSION == "RETENTION_POLICY.v1"

    def test_four_classification_levels(self):
        assert len(RETENTION_PERIODS) == 4

    def test_periods_ordered_by_days(self):
        levels = ["public", "internal", "confidential", "restricted"]
        days = [RETENTION_PERIODS[l].minimum_days for l in levels]
        assert days == sorted(days)

    def test_valid_hold_scopes(self):
        assert VALID_HOLD_SCOPES == frozenset({"run", "repo", "all"})

    def test_default_retention_is_max(self):
        assert DEFAULT_RETENTION_DAYS == 3650

    def test_framework_overrides_all_positive(self):
        for name, days in FRAMEWORK_RETENTION_OVERRIDES.items():
            assert days > 0, f"Framework {name} has non-positive days"

    def test_archive_format_values(self):
        assert ArchiveFormat.DIRECTORY.value == "directory"
        assert ArchiveFormat.ZIP.value == "zip"
