"""Tests for governance.domain.strict_exit_evaluator.

Covers the full blocking-grade decision matrix:

                    | missing       | stale          | below_threshold |
--------------------+---------------+----------------+-----------------+
critical: true      | BLOCKED       | BLOCKED        | BLOCKED         |
critical: false     | NOT_VERIFIED  | NOT_VERIFIED   | WARN            |

Plus non-strict mode (everything -> WARN/OK) and resolve_principal_strict().
"""

from datetime import datetime, timedelta, timezone

import pytest

from governance.domain.reason_codes import (
    BLOCKED_STRICT_EVIDENCE_MISSING,
    BLOCKED_STRICT_EVIDENCE_STALE,
    BLOCKED_STRICT_THRESHOLD,
    NOT_VERIFIED_STRICT_EVIDENCE_MISSING,
    NOT_VERIFIED_STRICT_EVIDENCE_STALE,
    REASON_CODE_NONE,
)
from governance.domain.strict_exit_evaluator import (
    CriterionResult,
    StrictExitResult,
    evaluate_strict_exit,
    get_threshold_resolver,
)
from governance.domain.models.policy_mode import resolve_principal_strict

NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
FRESH_TS = (NOW - timedelta(hours=1)).isoformat()
STALE_TS = (NOW - timedelta(hours=48)).isoformat()


def _criterion(
    artifact_kind: str,
    *,
    critical: bool = True,
    threshold_mode: str | None = None,
    threshold_resolver: str | None = None,
) -> dict:
    c: dict = {"artifact_kind": artifact_kind, "critical": critical}
    if threshold_mode is not None:
        c["threshold_mode"] = threshold_mode
    if threshold_resolver is not None:
        c["threshold_resolver"] = threshold_resolver
    return c


def _evidence(observed_at: str, value: object = None) -> dict:
    e: dict = {"observed_at": observed_at}
    if value is not None:
        e["value"] = value
    return e


# -----------------------------------------------------------------------
# Matrix: critical=True
# -----------------------------------------------------------------------


class TestCriticalTrue:
    """critical: true rows of the decision matrix."""

    def test_missing_evidence_blocks(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is True
        assert result.criteria[0].verdict == "blocked"
        assert result.criteria[0].reason_code == BLOCKED_STRICT_EVIDENCE_MISSING

    def test_stale_evidence_blocks(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={"test_quality_gate": _evidence(STALE_TS)},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is True
        assert result.criteria[0].verdict == "blocked"
        assert result.criteria[0].reason_code == BLOCKED_STRICT_EVIDENCE_STALE

    def test_below_threshold_blocks(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion(
                    "test_quality_gate",
                    critical=True,
                    threshold_mode="dynamic_by_risk_tier",
                    threshold_resolver="dynamic_by_risk_tier",
                )
            ],
            evidence_map={"test_quality_gate": _evidence(FRESH_TS, value=30.0)},
            risk_tier="high",
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is True
        assert result.criteria[0].verdict == "blocked"
        assert result.criteria[0].reason_code == BLOCKED_STRICT_THRESHOLD

    def test_fresh_above_threshold_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion(
                    "test_quality_gate",
                    critical=True,
                    threshold_mode="dynamic_by_risk_tier",
                    threshold_resolver="dynamic_by_risk_tier",
                )
            ],
            evidence_map={"test_quality_gate": _evidence(FRESH_TS, value=95.0)},
            risk_tier="high",
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "ok"

    def test_fresh_no_threshold_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={"test_quality_gate": _evidence(FRESH_TS)},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "ok"


# -----------------------------------------------------------------------
# Matrix: critical=False
# -----------------------------------------------------------------------


class TestCriticalFalse:
    """critical: false rows of the decision matrix."""

    def test_missing_evidence_not_verified(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("runtime_log", critical=False)],
            evidence_map={},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "not_verified"
        assert result.criteria[0].reason_code == NOT_VERIFIED_STRICT_EVIDENCE_MISSING

    def test_stale_evidence_not_verified(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("runtime_log", critical=False)],
            evidence_map={"runtime_log": _evidence(STALE_TS)},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "not_verified"
        assert result.criteria[0].reason_code == NOT_VERIFIED_STRICT_EVIDENCE_STALE

    def test_below_threshold_warns(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion(
                    "runtime_log",
                    critical=False,
                    threshold_mode="dynamic_by_risk_tier",
                    threshold_resolver="dynamic_by_risk_tier",
                )
            ],
            evidence_map={"runtime_log": _evidence(FRESH_TS, value=10.0)},
            risk_tier="high",
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "warn"

    def test_fresh_above_threshold_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion(
                    "runtime_log",
                    critical=False,
                    threshold_mode="dynamic_by_risk_tier",
                    threshold_resolver="dynamic_by_risk_tier",
                )
            ],
            evidence_map={"runtime_log": _evidence(FRESH_TS, value=90.0)},
            risk_tier="medium",
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "ok"


# -----------------------------------------------------------------------
# Non-strict mode: everything downgrades
# -----------------------------------------------------------------------


class TestNonStrictMode:
    """When principal_strict=False, nothing blocks — all degrade to warn/ok."""

    def test_missing_evidence_warns(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={},
            principal_strict=False,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "warn"

    def test_stale_evidence_warns(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={"test_quality_gate": _evidence(STALE_TS)},
            principal_strict=False,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "warn"

    def test_below_threshold_warns(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion(
                    "test_quality_gate",
                    critical=True,
                    threshold_mode="dynamic_by_risk_tier",
                    threshold_resolver="dynamic_by_risk_tier",
                )
            ],
            evidence_map={"test_quality_gate": _evidence(FRESH_TS, value=10.0)},
            risk_tier="high",
            principal_strict=False,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "warn"

    def test_fresh_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={"test_quality_gate": _evidence(FRESH_TS)},
            principal_strict=False,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria[0].verdict == "ok"


# -----------------------------------------------------------------------
# Multi-criteria aggregation
# -----------------------------------------------------------------------


class TestAggregation:
    """Multiple criteria: one blocked → aggregate blocked."""

    def test_one_blocked_one_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion("test_quality_gate", critical=True),
                _criterion("runtime_log", critical=False),
            ],
            evidence_map={
                "runtime_log": _evidence(FRESH_TS),
            },
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is True
        assert len(result.criteria) == 2
        verdicts = {r.criterion_key: r.verdict for r in result.criteria}
        assert verdicts["test_quality_gate"] == "blocked"
        assert verdicts["runtime_log"] == "ok"

    def test_all_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion("test_quality_gate", critical=True),
                _criterion("runtime_log", critical=False),
            ],
            evidence_map={
                "test_quality_gate": _evidence(FRESH_TS),
                "runtime_log": _evidence(FRESH_TS),
            },
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert all(r.verdict == "ok" for r in result.criteria)
        assert "OK" in result.summary

    def test_empty_criteria_ok(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[],
            evidence_map={},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is False
        assert result.criteria == ()
        assert "OK" in result.summary

    def test_reason_codes_aggregated(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion("test_quality_gate", critical=True),
                _criterion("risk_tier_assessment", critical=True),
            ],
            evidence_map={},
            principal_strict=True,
            now_utc=NOW,
        )
        assert len(result.reason_codes) == 2
        assert all(rc == BLOCKED_STRICT_EVIDENCE_MISSING for rc in result.reason_codes)


# -----------------------------------------------------------------------
# Threshold resolver
# -----------------------------------------------------------------------


class TestThresholdResolver:
    """Dynamic threshold resolver tests."""

    def test_builtin_resolver_exists(self) -> None:
        resolver = get_threshold_resolver("dynamic_by_risk_tier")
        assert resolver is not None

    def test_unknown_resolver_returns_none(self) -> None:
        assert get_threshold_resolver("nonexistent") is None

    def test_high_tier_threshold_80(self) -> None:
        resolver = get_threshold_resolver("dynamic_by_risk_tier")
        assert resolver is not None
        passed, detail = resolver("test_quality_gate", 79.9, "high")
        assert passed is False
        passed, detail = resolver("test_quality_gate", 80.0, "high")
        assert passed is True

    def test_low_tier_threshold_40(self) -> None:
        resolver = get_threshold_resolver("dynamic_by_risk_tier")
        assert resolver is not None
        passed, _ = resolver("test_quality_gate", 39.9, "low")
        assert passed is False
        passed, _ = resolver("test_quality_gate", 40.0, "low")
        assert passed is True

    def test_string_percentage_value(self) -> None:
        resolver = get_threshold_resolver("dynamic_by_risk_tier")
        assert resolver is not None
        passed, _ = resolver("test_quality_gate", "85%", "medium")
        assert passed is True

    def test_non_numeric_fails(self) -> None:
        resolver = get_threshold_resolver("dynamic_by_risk_tier")
        assert resolver is not None
        passed, detail = resolver("test_quality_gate", "N/A", "high")
        assert passed is False
        assert "non-numeric" in detail

    def test_unknown_resolver_in_criterion_strict_critical_blocks(self) -> None:
        """Unknown resolver + critical + strict → BLOCKED."""
        result = evaluate_strict_exit(
            pass_criteria=[
                _criterion(
                    "test_quality_gate",
                    critical=True,
                    threshold_mode="fantasy_resolver",
                    threshold_resolver="fantasy_resolver",
                )
            ],
            evidence_map={"test_quality_gate": _evidence(FRESH_TS, value=99.0)},
            principal_strict=True,
            now_utc=NOW,
        )
        assert result.blocked is True
        assert result.criteria[0].reason_code == BLOCKED_STRICT_THRESHOLD


# -----------------------------------------------------------------------
# resolve_principal_strict
# -----------------------------------------------------------------------


class TestResolvePrincipalStrict:
    """Fail-closed derivation of principal_strict flag."""

    def test_no_sources_returns_false(self) -> None:
        assert resolve_principal_strict() is False

    def test_profile_true(self) -> None:
        assert resolve_principal_strict(profile_strict=True) is True

    def test_profile_false(self) -> None:
        assert resolve_principal_strict(profile_strict=False) is False

    def test_override_true_overrides_profile_false(self) -> None:
        """Fail-closed: any True → True."""
        assert resolve_principal_strict(profile_strict=False, override_strict=True) is True

    def test_policy_true_overrides_all(self) -> None:
        assert resolve_principal_strict(
            profile_strict=False, override_strict=False, policy_strict=True
        ) is True

    def test_all_false(self) -> None:
        assert resolve_principal_strict(
            profile_strict=False, override_strict=False, policy_strict=False
        ) is False

    def test_none_sources_ignored(self) -> None:
        assert resolve_principal_strict(
            profile_strict=None, override_strict=None, policy_strict=True
        ) is True


# -----------------------------------------------------------------------
# StrictExitResult summary strings
# -----------------------------------------------------------------------


class TestSummary:
    def test_blocked_summary(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={},
            principal_strict=True,
            now_utc=NOW,
        )
        assert "BLOCKED" in result.summary

    def test_not_verified_summary(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("runtime_log", critical=False)],
            evidence_map={},
            principal_strict=True,
            now_utc=NOW,
        )
        assert "NOT_VERIFIED" in result.summary

    def test_warn_summary(self) -> None:
        result = evaluate_strict_exit(
            pass_criteria=[_criterion("test_quality_gate", critical=True)],
            evidence_map={},
            principal_strict=False,
            now_utc=NOW,
        )
        assert "WARN" in result.summary
