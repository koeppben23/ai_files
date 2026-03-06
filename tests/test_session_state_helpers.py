from __future__ import annotations

import pytest

from governance.application.use_cases.session_state_helpers import (
    _auto_propagate_gates,
    with_kernel_result,
)


def test_with_kernel_result_writes_session_state_kernel_block() -> None:
    updated = with_kernel_result(
        {"SESSION_STATE": {"RepoFingerprint": "abc"}},
        phase="3A-API-Inventory",
        next_token="3B-1",
        active_gate="API Inventory",
        next_gate_condition="Proceed",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={"phase_flow": "/tmp/commands/logs/flow.log.jsonl"},
        event_id="evt-1",
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    assert state["Phase"] == "3A-API-Inventory"
    assert state["Next"] == "3B-1"
    assert state["status"] == "OK"
    assert state["log_paths"] == {"phase_flow": "/tmp/commands/logs/flow.log.jsonl"}
    kernel = state["Kernel"]
    assert isinstance(kernel, dict)
    assert kernel["PhaseApiSha256"] == "deadbeef"
    assert kernel["PhaseApiLoadedAt"] == "2026-02-24T19:00:00+00:00"
    assert kernel["LastPhaseEventId"] == "evt-1"


def test_with_kernel_result_clamps_phase5_iteration_to_max() -> None:
    updated = with_kernel_result(
        {
            "SESSION_STATE": {
                "Phase5Review": {
                    "iteration": 9,
                    "max_iterations": 3,
                }
            }
        },
        phase="5-ArchitectureReview",
        next_token="5",
        active_gate="Architecture Review Gate",
        next_gate_condition="Continue",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={},
        event_id="evt-2",
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    phase5_review = state["Phase5Review"]
    assert isinstance(phase5_review, dict)
    assert phase5_review["iteration"] == 3
    assert phase5_review["max_iterations"] == 3


def test_with_kernel_result_clamps_implementation_iteration_to_max() -> None:
    updated = with_kernel_result(
        {
            "SESSION_STATE": {
                "ImplementationReview": {
                    "iteration": 7,
                    "max_iterations": 2,
                }
            }
        },
        phase="6-PostFlight",
        next_token="6",
        active_gate="Implementation Internal Review",
        next_gate_condition="Continue",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={},
        event_id="evt-3",
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    impl_review = state["ImplementationReview"]
    assert isinstance(impl_review, dict)
    assert impl_review["iteration"] == 2
    assert impl_review["max_iterations"] == 2


def test_with_kernel_result_writes_plan_record_gate_materialization_fields() -> None:
    updated = with_kernel_result(
        {"SESSION_STATE": {}},
        phase="5-ArchitectureReview",
        next_token="5",
        active_gate="Architecture Review Gate",
        next_gate_condition="Continue self-review loop",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={},
        event_id="evt-4",
        plan_record_status="active",
        plan_record_versions=1,
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    assert state["plan_record_status"] == "active"
    assert state["PlanRecordStatus"] == "active"
    assert state["plan_record_versions"] == 1
    assert state["PlanRecordVersions"] == 1


# ---------------------------------------------------------------------------
# Fix 2.1 — Conservative gate auto-propagation
# ---------------------------------------------------------------------------

_KERNEL_DEFAULTS = dict(
    active_gate="Test",
    next_gate_condition="Test",
    spec_hash="deadbeef",
    spec_path="/tmp/phase_api.yaml",
    spec_loaded_at="2026-03-06T00:00:00+00:00",
    log_paths={},
    event_id="evt-gate",
)


class TestGateAutoPropagation:
    """Tests for _auto_propagate_gates via with_kernel_result (Fix 2.1)."""

    # --- Happy path: P5-Architecture propagates when reaching 5.3+ ---

    def test_p5_architecture_propagates_at_token_5_3(self) -> None:
        """When next_token=5.3 and status=OK, P5-Architecture upgrades
        from 'pending' to 'approved'."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "pending", "P5.3-TestQuality": "pending"}}},
            phase="5.3-TestQuality",
            next_token="5.3",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        gates = updated["SESSION_STATE"]["Gates"]
        assert gates["P5-Architecture"] == "approved"
        # P5.3 should NOT be propagated at 5.3 (needs 5.4+)
        assert gates["P5.3-TestQuality"] == "pending"

    def test_p5_architecture_and_p53_propagate_at_token_6(self) -> None:
        """When next_token=6 and status=OK, both P5-Architecture and
        P5.3-TestQuality are upgraded."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
                "P5.4-BusinessRules": "pending",
                "P5.6-RollbackSafety": "pending",
            }}},
            phase="6-PostFlight",
            next_token="6",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        gates = updated["SESSION_STATE"]["Gates"]
        assert gates["P5-Architecture"] == "approved"
        assert gates["P5.3-TestQuality"] == "pass"
        # P5.4 and P5.6 are NOT auto-propagated (conditional gates).
        assert gates["P5.4-BusinessRules"] == "pending"
        assert gates["P5.6-RollbackSafety"] == "pending"

    def test_p53_propagates_at_token_5_4(self) -> None:
        """When next_token=5.4, P5.3-TestQuality upgrades to 'pass'."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
            }}},
            phase="5.4-BusinessRules",
            next_token="5.4",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        gates = updated["SESSION_STATE"]["Gates"]
        assert gates["P5-Architecture"] == "approved"
        assert gates["P5.3-TestQuality"] == "pass"

    # --- Corner: non-pending gates are never overwritten ---

    def test_does_not_downgrade_already_approved_architecture(self) -> None:
        """A gate already set to a non-pending value must not be touched."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "approved"}}},
            phase="5.3-TestQuality",
            next_token="5.3",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        assert updated["SESSION_STATE"]["Gates"]["P5-Architecture"] == "approved"

    def test_does_not_overwrite_p53_pass_with_exceptions(self) -> None:
        """P5.3 already set to 'pass-with-exceptions' is not overwritten."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5.3-TestQuality": "pass-with-exceptions"}}},
            phase="6-PostFlight",
            next_token="6",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        assert updated["SESSION_STATE"]["Gates"]["P5.3-TestQuality"] == "pass-with-exceptions"

    def test_does_not_overwrite_p5_fail_status(self) -> None:
        """Even if next_token is past 5.3, a 'fail' gate is not overwritten."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "fail"}}},
            phase="5.3-TestQuality",
            next_token="5.3",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        assert updated["SESSION_STATE"]["Gates"]["P5-Architecture"] == "fail"

    # --- Edge: status not OK → no propagation ---

    def test_no_propagation_when_status_blocked(self) -> None:
        """Gates should not be propagated when kernel status is BLOCKED."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "pending"}}},
            phase="5.3-TestQuality",
            next_token="5.3",
            status="BLOCKED",
            **_KERNEL_DEFAULTS,
        )
        assert updated["SESSION_STATE"]["Gates"]["P5-Architecture"] == "pending"

    # --- Edge: no Gates dict → no crash ---

    def test_no_crash_without_gates_dict(self) -> None:
        """If SESSION_STATE has no Gates dict, propagation is silently skipped."""
        updated = with_kernel_result(
            {"SESSION_STATE": {}},
            phase="5.3-TestQuality",
            next_token="5.3",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        # Should not create a Gates dict from scratch.
        assert "Gates" not in updated["SESSION_STATE"]

    # --- Edge: next_token before gate threshold → no propagation ---

    def test_no_propagation_at_token_5(self) -> None:
        """Phase 5 (architecture review) is too early for any gate propagation."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "pending", "P5.3-TestQuality": "pending"}}},
            phase="5-ArchitectureReview",
            next_token="5",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        gates = updated["SESSION_STATE"]["Gates"]
        assert gates["P5-Architecture"] == "pending"
        assert gates["P5.3-TestQuality"] == "pending"

    # --- Edge: next_token=None → no propagation ---

    def test_no_propagation_with_none_next_token(self) -> None:
        """next_token=None means no phase progression info — skip."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "pending"}}},
            phase="5-ArchitectureReview",
            next_token=None,
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        assert updated["SESSION_STATE"]["Gates"]["P5-Architecture"] == "pending"

    # --- Bad path: unknown token → no propagation ---

    def test_no_propagation_for_unknown_token(self) -> None:
        """An unrecognized token (rank -1) should not trigger any propagation."""
        updated = with_kernel_result(
            {"SESSION_STATE": {"Gates": {"P5-Architecture": "pending"}}},
            phase="unknown",
            next_token="unknown",
            status="OK",
            **_KERNEL_DEFAULTS,
        )
        assert updated["SESSION_STATE"]["Gates"]["P5-Architecture"] == "pending"


class TestAutoGatesUnit:
    """Direct unit tests for _auto_propagate_gates (Fix 2.1)."""

    def test_propagates_both_gates_at_token_5_6(self) -> None:
        """Token 5.6 is past both 5.3 and 5.4 thresholds."""
        ss: dict[str, object] = {"Gates": {
            "P5-Architecture": "pending",
            "P5.3-TestQuality": "pending",
        }}
        _auto_propagate_gates(ss, status="OK", next_token="5.6")
        assert ss["Gates"]["P5-Architecture"] == "approved"
        assert ss["Gates"]["P5.3-TestQuality"] == "pass"

    def test_whitespace_pending_still_matches(self) -> None:
        """Gate values with whitespace like ' pending ' should still match."""
        ss: dict[str, object] = {"Gates": {"P5-Architecture": " Pending "}}
        _auto_propagate_gates(ss, status="OK", next_token="5.3")
        assert ss["Gates"]["P5-Architecture"] == "approved"

    def test_gates_not_dict_is_noop(self) -> None:
        """If Gates is a string or list, propagation is silently skipped."""
        ss: dict[str, object] = {"Gates": "broken"}
        _auto_propagate_gates(ss, status="OK", next_token="6")
        assert ss["Gates"] == "broken"
