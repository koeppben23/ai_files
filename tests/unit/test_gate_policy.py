from datetime import datetime, timezone

from governance.domain.policies.gate_policy import persistence_gate, rulebook_gate, strict_exit_gate
from governance.domain.reason_codes import (
    BLOCKED_STRICT_EVIDENCE_MISSING,
    BLOCKED_STRICT_EVIDENCE_STALE,
    BLOCKED_STRICT_THRESHOLD,
    NOT_VERIFIED_STRICT_EVIDENCE_MISSING,
)


def test_persistence_gate_fail_closed_missing_flags() -> None:
    result = persistence_gate({})
    assert result.ok is False


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


# ---------------------------------------------------------------------------
# strict_exit_gate tests
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
_FRESH_TS = "2026-03-01T11:59:00Z"
_STALE_TS = "2025-01-01T00:00:00Z"


def test_strict_exit_gate_blocks_on_critical_missing_evidence() -> None:
    """Critical criterion + missing evidence + strict → BLOCKED."""
    criteria = [{"criterion_key": "C1", "artifact_kind": "test_result", "critical": True}]
    result = strict_exit_gate(
        pass_criteria=criteria,
        evidence_map={},
        now_utc=_NOW,
        principal_strict=True,
    )
    assert result.blocked is True
    assert BLOCKED_STRICT_EVIDENCE_MISSING in result.reason_codes


def test_strict_exit_gate_not_blocked_non_strict() -> None:
    """Same criterion but non-strict → WARN, not blocked."""
    criteria = [{"criterion_key": "C1", "artifact_kind": "test_result", "critical": True}]
    result = strict_exit_gate(
        pass_criteria=criteria,
        evidence_map={},
        now_utc=_NOW,
        principal_strict=False,
    )
    assert result.blocked is False


def test_strict_exit_gate_ok_with_fresh_evidence() -> None:
    """All evidence present and fresh → OK."""
    criteria = [{"criterion_key": "C1", "artifact_kind": "test_result", "critical": True}]
    evidence = {"test_result": {"observed_at": _FRESH_TS, "value": 100}}
    result = strict_exit_gate(
        pass_criteria=criteria,
        evidence_map=evidence,
        now_utc=_NOW,
        principal_strict=True,
    )
    assert result.blocked is False
    assert len(result.reason_codes) == 0


def test_strict_exit_gate_non_critical_missing_is_not_verified() -> None:
    """Non-critical + missing evidence + strict → NOT_VERIFIED."""
    criteria = [{"criterion_key": "C1", "artifact_kind": "test_result", "critical": False}]
    result = strict_exit_gate(
        pass_criteria=criteria,
        evidence_map={},
        now_utc=_NOW,
        principal_strict=True,
    )
    assert result.blocked is False
    assert NOT_VERIFIED_STRICT_EVIDENCE_MISSING in result.reason_codes


def test_strict_exit_gate_delegates_risk_tier() -> None:
    """Risk tier is forwarded to the threshold resolver."""
    criteria = [{
        "criterion_key": "C1",
        "artifact_kind": "test_result",
        "critical": True,
        "threshold_mode": "dynamic_by_risk_tier",
        "threshold_resolver": "dynamic_by_risk_tier",
    }]
    # Value 50 passes for low (40%) but fails for high (80%)
    evidence = {"test_result": {"observed_at": _FRESH_TS, "value": 50}}
    result_high = strict_exit_gate(
        pass_criteria=criteria,
        evidence_map=evidence,
        risk_tier="high",
        now_utc=_NOW,
        principal_strict=True,
    )
    result_low = strict_exit_gate(
        pass_criteria=criteria,
        evidence_map=evidence,
        risk_tier="low",
        now_utc=_NOW,
        principal_strict=True,
    )
    assert result_high.blocked is True
    assert BLOCKED_STRICT_THRESHOLD in result_high.reason_codes
    assert result_low.blocked is False
