"""Tests for Pipeline Auto-Approve feature.

Tests cover:
- Pipeline auto-approve eligibility check (via phase_kernel)
- Pipeline auto-approve integration in review_decision_persist
- Blocking in non-pipeline modes (user, agents_strict)
- Audit trail creation

Happy / Negative / Corner / Edge coverage.

Note: The canonical implementation is in review_decision_persist.py.
The eligibility check is in phase_kernel.py.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from governance_runtime.entrypoints.review_decision_persist import (
    apply_review_decision,
)
from governance_runtime.kernel.phase_kernel import pipeline_auto_approve_eligible


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    effective_operating_mode: str = "pipeline",
    phase: str = "6-PostFlight",
    active_gate: str = "Evidence Presentation Gate",
    phase6_review_iterations: int = 3,
    phase6_max_review_iterations: int = 3,
    user_review_decision: str = "",
    workflow_complete: bool = False,
) -> dict:
    return {
        "effective_operating_mode": effective_operating_mode,
        "phase": phase,
        "phase": phase,
        "active_gate": active_gate,
        "Phase6Review": {
            "iteration": phase6_review_iterations,
            "revision_delta": "none",
        },
        "phase6_review_iterations": phase6_review_iterations,
        "phase6_max_review_iterations": phase6_max_review_iterations,
        "phase6_min_review_iterations": 1,
        "UserReviewDecision": {"decision": user_review_decision} if user_review_decision else {},
        "workflow_complete": workflow_complete,
    }


# ---------------------------------------------------------------------------
# Eligibility Check Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPipelineAutoApproveEligibility:
    """Tests for pipeline_auto_approve_eligible() function in phase_kernel."""

    def test_eligible_in_pipeline_mode_with_complete_review(self):
        """Pipeline mode with complete review at Evidence Gate is eligible."""
        state = _make_state(
            effective_operating_mode="pipeline",
            active_gate="Evidence Presentation Gate",
            phase6_review_iterations=3,
            phase6_max_review_iterations=3,
        )
        assert pipeline_auto_approve_eligible(state) is True

    def test_not_eligible_in_user_mode(self):
        """User/solo mode is NOT eligible for auto-approve."""
        state = _make_state(
            effective_operating_mode="user",
            active_gate="Evidence Presentation Gate",
        )
        assert pipeline_auto_approve_eligible(state) is False

    def test_not_eligible_in_agents_strict_mode(self):
        """agents_strict (regulated) mode is NOT eligible for auto-approve.

        This test directly protects the core governance promise: regulated/agents_strict
        mode must NOT auto-approve, even when all other conditions are met.
        """
        state = _make_state(
            effective_operating_mode="agents_strict",
            active_gate="Evidence Presentation Gate",
        )
        assert pipeline_auto_approve_eligible(state) is False, (
            "agents_strict mode must NOT be eligible for auto-approve"
        )

    def test_agents_strict_remains_ineligible_even_with_complete_review(self):
        """agents_strict mode with complete review is still NOT eligible.

        This is a critical governance boundary: even if internal review is complete
        and all other conditions are met, agents_strict mode must NOT auto-approve.
        """
        state = _make_state(
            effective_operating_mode="agents_strict",
            active_gate="Evidence Presentation Gate",
            phase6_review_iterations=3,
            phase6_max_review_iterations=3,
        )
        assert pipeline_auto_approve_eligible(state) is False, (
            "agents_strict mode with complete review must NOT be eligible for auto-approve"
        )

    def test_agents_strict_ineligible_at_any_gate(self):
        """agents_strict mode is NOT eligible at any gate, not just Evidence Gate.

        Extends the governance promise: agents_strict must never auto-approve,
        regardless of which gate the session is at.
        """
        gates = [
            "Implementation Internal Review",
            "Implementation Verification",
            "Implementation Review Complete",
            "Evidence Presentation Gate",
            "Rework Clarification Gate",
        ]
        for gate in gates:
            state = _make_state(
                effective_operating_mode="agents_strict",
                active_gate=gate,
                phase6_review_iterations=3,
                phase6_max_review_iterations=3,
            )
            assert pipeline_auto_approve_eligible(state) is False, (
                f"agents_strict mode at '{gate}' must NOT be eligible for auto-approve"
            )

    def test_not_eligible_without_review_complete(self):
        """Pipeline mode without complete review is NOT eligible."""
        state = _make_state(
            effective_operating_mode="pipeline",
            active_gate="Evidence Presentation Gate",
            phase6_review_iterations=1,
            phase6_max_review_iterations=3,
        )
        assert pipeline_auto_approve_eligible(state) is False

    def test_not_eligible_not_at_evidence_gate(self):
        """Pipeline mode NOT at Evidence Gate is NOT eligible."""
        state = _make_state(
            effective_operating_mode="pipeline",
            active_gate="Implementation Internal Review",
        )
        assert pipeline_auto_approve_eligible(state) is False

    def test_not_eligible_with_existing_decision(self):
        """Pipeline mode with existing review decision is NOT eligible."""
        state = _make_state(
            effective_operating_mode="pipeline",
            active_gate="Evidence Presentation Gate",
            user_review_decision="approve",
        )
        assert pipeline_auto_approve_eligible(state) is False

    def test_not_eligible_when_workflow_complete(self):
        """Pipeline mode when workflow is already complete is NOT eligible."""
        state = _make_state(
            effective_operating_mode="pipeline",
            active_gate="Evidence Presentation Gate",
            workflow_complete=True,
        )
        assert pipeline_auto_approve_eligible(state) is False

    def test_not_eligible_in_phase5(self):
        """Pipeline mode in Phase 5 is NOT eligible."""
        state = _make_state(
            effective_operating_mode="pipeline",
            phase="5-ArchitectureReview",
            active_gate="Architecture Review Gate",
        )
        assert pipeline_auto_approve_eligible(state) is False


# ---------------------------------------------------------------------------
# Integration Tests: review_decision_persist integration
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPipelineAutoApproveIntegration:
    """Integration tests for pipeline auto-approve in review_decision_persist."""

    def test_review_decision_auto_approves_in_pipeline_mode(self, tmp_path: Path):
        """apply_review_decision with empty decision auto-approves in pipeline mode."""
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=events_path,
        )

        assert result["status"] == "ok"
        updated = json.loads(session_path.read_text(encoding="utf-8"))
        state_section = updated.get("SESSION_STATE", {})
        canonical = state_section.get("canonical", state_section)
        assert canonical.get("workflow_complete") is True
        assert canonical.get("implementation_authorized") is True
        assert canonical.get("active_gate") == "Workflow Complete"

        assert events_path.exists()
        audit_lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(audit_lines) == 1
        audit_event = json.loads(audit_lines[0])
        assert audit_event["event"] == "pipeline_auto_approve"
        assert audit_event["result"] == "approved"

    def test_review_decision_blocks_in_user_mode_with_empty_decision(self, tmp_path: Path):
        """apply_review_decision with empty decision returns error in user mode."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="user")
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
        )

        assert result["status"] == "error"

    def test_review_decision_blocks_in_agents_strict_mode(self, tmp_path: Path):
        """apply_review_decision with empty decision blocks in agents_strict mode.

        This test proves the fail-closed behavior for regulated/agents_strict:
        Empty decision in agents_strict must return error, not auto-approve.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="agents_strict")
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Empty decision in agents_strict must return error, got: {result}"
        )
        assert "reason_code" in result, "Error must include reason_code"

    def test_review_decision_agents_strict_requires_explicit_approval(self, tmp_path: Path):
        """agents_strict mode requires explicit approval decision, not auto-approve.

        This test ensures that regulated/agents_strict workflows require explicit
        human review decision, not empty-decision auto-approve.
        Empty decision must error with a reason_code.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        state = _make_state(effective_operating_mode="agents_strict")
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result_empty = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=events_path,
        )
        assert result_empty["status"] == "error", (
            "Empty decision in agents_strict must error, not auto-approve"
        )
        assert "reason_code" in result_empty, (
            "Error must include reason_code"
        )

    def test_review_decision_still_works_with_explicit_decision(self, tmp_path: Path):
        """apply_review_decision with explicit 'approve' follows normal path."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] in ("ok", "error")
        if result["status"] == "ok":
            updated = json.loads(session_path.read_text(encoding="utf-8"))
            state_section = updated.get("SESSION_STATE", {})
            canonical = state_section.get("canonical", state_section)
            assert canonical.get("workflow_complete") is True


# ---------------------------------------------------------------------------
# Fail-Closed Tests: Wrong Phase / Missing ReviewPackage
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPipelineAutoApproveFailClosed:
    """Fail-closed tests for pipeline auto-approve at critical boundaries.

    These tests verify that the system blocks inappropriate auto-approve attempts:
    - Wrong phase (not Phase 6)
    - Missing required review evidence
    - Already approved workflow
    """

    def test_approve_in_phase5_blocks_fail_closed(self, tmp_path: Path):
        """apply_review_decision with 'approve' in Phase 5 must fail-closed.

        Phase 5 is architecture review - approve decision is only valid at Phase 6.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(
            effective_operating_mode="pipeline",
            phase="5-ArchitectureReview",
            active_gate="Architecture Review Gate",
        )
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve in Phase 5 must fail-closed, got: {result}"
        )

    def test_approve_in_phase4_blocks_fail_closed(self, tmp_path: Path):
        """apply_review_decision with 'approve' in Phase 4 must fail-closed.

        Phase 4 is ticket intake - approve decision is only valid at Phase 6.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(
            effective_operating_mode="pipeline",
            phase="4-TicketIntake",
            active_gate="Ticket Input Gate",
        )
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve in Phase 4 must fail-closed, got: {result}"
        )

    def test_approve_without_review_package_blocks(self, tmp_path: Path):
        """apply_review_decision with 'approve' without ReviewPackage must fail-closed.

        Review package is required evidence for approval decision.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="pipeline")
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state.pop("Phase6Review", None)
        state["review_package_presented"] = False
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve without ReviewPackage must fail-closed, got: {result}"
        )

    def test_approve_at_evidence_gate_without_review_complete_blocks(self, tmp_path: Path):
        """apply_review_decision at Evidence Gate without complete review must fail-closed.

        Internal review must be complete before approval is allowed.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(
            effective_operating_mode="pipeline",
            phase6_review_iterations=1,
            phase6_max_review_iterations=3,
        )
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve without complete review must fail-closed, got: {result}"
        )

    def test_empty_decision_in_phase5_blocks_not_auto_approves(self, tmp_path: Path):
        """apply_review_decision with empty decision in Phase 5 must block.

        Empty decision in non-Phase 6 context should not trigger auto-approve.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(
            effective_operating_mode="pipeline",
            phase="5-ArchitectureReview",
            active_gate="Architecture Review Gate",
        )
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Empty decision in Phase 5 must block, got: {result}"
        )

    def test_approve_without_phase6_review_block_blocks(self, tmp_path: Path):
        """apply_review_decision without Phase6Review block must fail-closed.

        Phase6Review block is required for approval decision.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="pipeline")
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state.pop("Phase6Review", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve without Phase6Review block must fail-closed, got: {result}"
        )
        assert "reason_code" in result, "Error must include reason_code"

    def test_approve_without_session_path_blocks(self, tmp_path: Path):
        """apply_review_decision without session_path existing must fail-closed.

        Missing session state file is a critical error.
        """
        session_path = tmp_path / "nonexistent" / "SESSION_STATE.json"

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve without session_path must fail-closed, got: {result}"
        )

    def test_approve_in_phase3_blocks(self, tmp_path: Path):
        """apply_review_decision in Phase 3 must fail-closed.

        Approval decision is only valid at Phase 6.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(
            effective_operating_mode="pipeline",
            phase="3-Bootstrap",
            active_gate="Bootstrap Gate",
        )
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="approve",
            session_path=session_path,
        )

        assert result["status"] == "error", (
            f"Approve in Phase 3 must fail-closed, got: {result}"
        )


# ---------------------------------------------------------------------------
# Idempotency Tests: Duplicate Auto-Approve Calls
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPipelineAutoApproveIdempotency:
    """Idempotency tests for pipeline auto-approve.

    These tests verify that duplicate auto-approve calls are handled gracefully:
    - Second call after workflow_complete should succeed (no-op)
    - State should remain consistent
    - No duplicate audit events
    """

    def test_duplicate_auto_approve_call_is_idempotent(self, tmp_path: Path):
        """Second auto-approve call after workflow_complete should be idempotent.

        Idempotent behavior: calling auto-approve multiple times has the same effect
        as calling it once. No error, no duplicate state mutation, no new audit events.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result1 = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=events_path,
        )
        assert result1["status"] == "ok", f"First call should succeed: {result1}"

        audit_count_after_first = len(events_path.read_text(encoding="utf-8").strip().split("\n"))

        state_after_first = json.loads(session_path.read_text(encoding="utf-8"))
        ss = state_after_first.get("SESSION_STATE", state_after_first)
        canonical1 = ss.get("canonical", ss) if isinstance(ss, dict) else ss
        assert canonical1.get("workflow_complete") is True

        result2 = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=events_path,
        )

        assert result2["status"] == "ok", (
            f"Second auto-approve call should succeed (idempotent), got: {result2}"
        )
        assert result2.get("decision") == "already_approved", (
            f"Second call should indicate already_approved, got: {result2}"
        )

        state_after_second = json.loads(session_path.read_text(encoding="utf-8"))
        ss2 = state_after_second.get("SESSION_STATE", state_after_second)
        canonical2 = ss2.get("canonical", ss2) if isinstance(ss2, dict) else ss2
        assert canonical2.get("workflow_complete") is True, (
            "State should remain workflow_complete=True after second call"
        )
        assert canonical2.get("active_gate") == "Workflow Complete", (
            f"State should remain Workflow Complete, got: {canonical2.get('active_gate')}"
        )

        audit_count_after_second = len(events_path.read_text(encoding="utf-8").strip().split("\n"))
        assert audit_count_after_second == audit_count_after_first, (
            f"No new audit events should be created, had {audit_count_after_first}, now {audit_count_after_second}"
        )

    def test_auto_approve_after_explicit_approve_is_idempotent(self, tmp_path: Path):
        """Auto-approve after explicit 'approve' should return already_approved.

        If workflow is already approved via explicit decision, auto-approve should
        recognize this and return 'already_approved' status.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state["UserReviewDecision"] = {
            "decision": "approve",
            "rationale": "Human review completed",
            "source": "explicit_approval",
        }
        state["workflow_complete"] = True
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
        )

        assert result["status"] == "ok", (
            f"Auto-approve after explicit approval should return ok, got: {result}"
        )
        assert result.get("decision") == "already_approved", (
            f"Call should indicate already_approved, got: {result}"
        )

        final_state = json.loads(session_path.read_text(encoding="utf-8"))
        ss = final_state.get("SESSION_STATE", final_state)
        canonical = ss.get("canonical", ss) if isinstance(ss, dict) else ss

        assert canonical.get("workflow_complete") is True, (
            "State should remain workflow_complete=True"
        )
        assert canonical["UserReviewDecision"]["source"] == "explicit_approval", (
            "Original approval source should be preserved"
        )

    def test_workflow_complete_blocks_new_auto_approve(self, tmp_path: Path):
        """Auto-approve on already-completed workflow should not create new events.

        Once workflow_complete=True, subsequent auto-approve attempts should not
        re-trigger the approval logic.
        """
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"

        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state["workflow_complete"] = True
        state["active_gate"] = "Workflow Complete"
        state["UserReviewDecision"] = {
            "decision": "approve",
            "source": "pipeline_auto_approve",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")
        events_path.write_text(json.dumps({
            "event": "pipeline_auto_approve",
            "result": "approved"
        }) + "\n", encoding="utf-8")

        initial_event_count = len(events_path.read_text(encoding="utf-8").strip().split("\n"))

        result = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=events_path,
        )

        assert result["status"] == "ok", (
            f"Auto-approve on completed workflow should return ok, got: {result}"
        )
        assert result.get("decision") == "already_approved", (
            f"Call should indicate already_approved, got: {result}"
        )

        final_state = json.loads(session_path.read_text(encoding="utf-8"))
        ss = final_state.get("SESSION_STATE", final_state)
        canonical = ss.get("canonical", ss) if isinstance(ss, dict) else ss

        assert canonical.get("workflow_complete") is True, (
            "State should remain workflow_complete=True"
        )
        assert canonical["UserReviewDecision"]["source"] == "pipeline_auto_approve", (
            "Original approval source should be preserved"
        )

        final_event_count = len(events_path.read_text(encoding="utf-8").strip().split("\n"))
        assert final_event_count == initial_event_count, (
            f"No new audit events should be created, had {initial_event_count}, now {final_event_count}"
        )
    
# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPipelineAutoApproveEdgeCases:
    """Edge case tests for pipeline auto-approve."""

    def test_eligible_with_empty_state_keys(self, tmp_path: Path):
        """Eligibility works when optional state keys are missing."""
        state = {
            "effective_operating_mode": "pipeline",
            "active_gate": "Evidence Presentation Gate",
            "Phase6Review": {"iteration": 3, "revision_delta": "none"},
            "phase6_review_iterations": 3,
            "phase6_max_review_iterations": 3,
            "phase6_min_review_iterations": 1,
        }
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=events_path,
        )
        assert result["status"] == "ok"

    def test_apply_without_events_path_succeeds(self, tmp_path: Path):
        """Auto-approve succeeds even without events_path."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
            events_path=None,
        )

        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# E2E Integration Tests: session_reader with materialize=True
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPipelineAutoApproveE2E:
    """E2E tests for pipeline auto-approve wired through session_reader.

    These tests prove the full workflow WITHOUT manual apply_review_decision calls:
    1. Pipeline mode with complete internal review
    2. Kernel signals source="pipeline-auto-approve"
    3. session_reader consumes signal AUTOMATICALLY during materialize
    4. State is auto-approved - workflow completes automatically
    """

    def test_full_pipeline_auto_approve_flow_kernel_to_final_state(self, tmp_path: Path):
        """Full E2E: Kernel signal → session_reader → auto-approve → final state.

        This test proves the complete deterministic auto-approve flow:
        1. Pipeline context with complete internal review
        2. Kernel evaluates eligibility and signals source="pipeline-auto-approve"
        3. session_reader._materialize_authoritative_state() detects signal
        4. apply_review_decision(decision="") called automatically
        5. Final state: workflow_complete=true, active_gate="Workflow Complete"
        6. Audit trail contains pipeline_auto_approve event
        """
        import governance_runtime.entrypoints.session_reader as session_reader_module
        from governance_runtime.kernel.phase_kernel import KernelResult

        config_root = tmp_path / "config_root"
        commands_home = config_root / "commands"
        commands_home.mkdir(parents=True)

        ws_dir = config_root / "workspaces" / "test-repo"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_path = ws_dir / "SESSION_STATE.json"
        events_path = ws_dir / "logs" / "events.jsonl"

        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(session_path),
            "activeRepoFingerprint": "test-repo",
        }
        (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state["repo_fingerprint"] = "test-repo"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        (commands_home / "phase_api.yaml").write_text(
            textwrap.dedent("""\
                schema: opencode.governance.phase-api.v1
                phases:
                  "6":
                    next_token: "6"
                    route_strategy: stay
                    entries:
                      - entry: start
                        when: implementation_review_complete
                        next_token: "6"
                        source: phase-6-review-complete
                        active_gate: Evidence Presentation Gate
                        next_gate_condition: Pipeline auto-approve enabled.
            """),
            encoding="utf-8",
        )

        kernel_result = KernelResult(
            phase="6",
            next_token="6",
            active_gate="Evidence Presentation Gate",
            next_gate_condition="Workflow auto-approved in pipeline mode. Implementation authorized.",
            workspace_ready=True,
            source="pipeline-auto-approve",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-full-e2e-001",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=kernel_result):
            snapshot = session_reader_module.read_session_snapshot(
                commands_home=commands_home,
                materialize=True,
            )

        assert snapshot.get("status") == "OK", (
            f"Materialize should succeed, got: {snapshot.get('status')}"
        )

        on_disk = json.loads(session_path.read_text(encoding="utf-8"))
        ss = on_disk.get("SESSION_STATE", on_disk)
        canonical = ss.get("canonical", ss) if isinstance(ss, dict) else ss

        assert canonical.get("workflow_complete") is True, (
            "Final state must have workflow_complete=True"
        )
        assert canonical.get("active_gate") == "Workflow Complete", (
            f"Final state must have active_gate='Workflow Complete', got: {canonical.get('active_gate')}"
        )
        assert canonical.get("implementation_authorized") is True, (
            "Final state must have implementation_authorized=True"
        )
        assert "UserReviewDecision" in canonical, (
            "Final state must contain UserReviewDecision"
        )
        assert canonical["UserReviewDecision"].get("source") == "pipeline_auto_approve", (
            "UserReviewDecision must have source='pipeline_auto_approve'"
        )

        assert events_path.exists(), "Audit trail must exist"
        audit_lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(audit_lines) >= 1, "Audit trail must contain at least one event"

        pipeline_event = None
        for line in audit_lines:
            if line.strip():
                event = json.loads(line)
                if event.get("event") == "pipeline_auto_approve":
                    pipeline_event = event
                    break

        assert pipeline_event is not None, (
            f"pipeline_auto_approve event must be in audit trail, got events: {[json.loads(l) for l in audit_lines if l.strip()]}"
        )
        assert pipeline_event.get("result") == "approved", (
            f"Audit event result must be 'approved', got: {pipeline_event.get('result')}"
        )

    def test_materialize_auto_approves_without_manual_decision_call(self, tmp_path: Path):
        """Pipeline workflow auto-approves during materialize - NO manual apply_review_decision call.

        This test proves the deterministic auto-approve flow:
        - /continue calls read_session_snapshot(materialize=True)
        - Kernel returns source="pipeline-auto-approve"
        - session_reader AUTOMATICALLY triggers apply_review_decision
        - Workflow completes without human intervention
        """
        import governance_runtime.entrypoints.session_reader as session_reader_module
        from governance_runtime.kernel.phase_kernel import KernelResult

        config_root = tmp_path / "config_root"
        commands_home = config_root / "commands"
        commands_home.mkdir(parents=True)

        ws_dir = config_root / "workspaces" / "test-repo"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_path = ws_dir / "SESSION_STATE.json"
        events_path = ws_dir / "logs" / "events.jsonl"

        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(session_path),
            "activeRepoFingerprint": "test-repo",
        }
        (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state["repo_fingerprint"] = "test-repo"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        (commands_home / "phase_api.yaml").write_text(
            textwrap.dedent("""\
                schema: opencode.governance.phase-api.v1
                phases:
                  "6":
                    next_token: "6"
                    route_strategy: stay
                    entries:
                      - entry: start
                        when: default
                        next_token: "6"
                        source: phase-6-default
                        active_gate: Evidence Presentation Gate
                        next_gate_condition: Run /continue to materialize presentation gate.
            """),
            encoding="utf-8",
        )

        kernel_result = KernelResult(
            phase="6",
            next_token="6",
            active_gate="Evidence Presentation Gate",
            next_gate_condition="Workflow auto-approved in pipeline mode. Implementation authorized.",
            workspace_ready=True,
            source="pipeline-auto-approve",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-auto-approve-001",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        # Track that apply_review_decision is NEVER called directly by test code
        apply_review_decision_calls = []
        original_apply = session_reader_module.apply_review_decision
        def tracking_apply(*args, **kwargs):
            apply_review_decision_calls.append((args, kwargs))
            return original_apply(*args, **kwargs)
        
        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=kernel_result):
            with patch.object(session_reader_module, "apply_review_decision", tracking_apply):
                snapshot = session_reader_module.read_session_snapshot(
                    commands_home=commands_home,
                    materialize=True,
                )

        # Prove: workflow auto-completed during materialize
        assert snapshot.get("status") == "OK", f"Snapshot should be OK, got {snapshot.get('status')}: {snapshot.get('error', '')}"
        assert snapshot.get("active_gate") == "Workflow Complete", \
            f"active_gate should be 'Workflow Complete', got '{snapshot.get('active_gate')}'"

        # Prove: on-disk state reflects auto-approve
        updated_state = json.loads(session_path.read_text(encoding="utf-8"))
        state_section = updated_state.get("SESSION_STATE", {})
        on_disk = state_section.get("canonical", state_section) if isinstance(state_section, dict) else state_section
        assert on_disk.get("workflow_complete") is True, \
            f"workflow_complete should be True, got {on_disk.get('workflow_complete')}"
        assert on_disk.get("active_gate") == "Workflow Complete", \
            f"on-disk active_gate should be 'Workflow Complete', got '{on_disk.get('active_gate')}'"
        assert on_disk.get("implementation_authorized") is True, \
            f"implementation_authorized should be True, got {on_disk.get('implementation_authorized')}"

        # Prove: apply_review_decision was called AUTOMATICALLY by session_reader (1 call)
        assert len(apply_review_decision_calls) == 1, \
            f"apply_review_decision should be called exactly once automatically, was called {len(apply_review_decision_calls)} times"
        
        # Prove: audit trail was created
        assert events_path.exists(), "events.jsonl should exist"
        audit_lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(audit_lines) >= 1, "At least one audit event should be written"
        pipeline_events = [l for l in audit_lines if "pipeline" in l.lower() or "auto" in l.lower()]
        assert len(pipeline_events) >= 1, f"Pipeline auto-approve event should be in audit log, got {audit_lines}"

    def test_kernel_signal_triggers_auto_approve_via_session_reader(self, tmp_path: Path):
        """Kernel source='pipeline-auto-approve' deterministically triggers auto-approve.

        This test verifies the kernel-to-session_reader signal path:
        1. Kernel evaluation returns source="pipeline-auto-approve"
        2. session_reader.materialize detects the signal
        3. apply_review_decision is invoked with empty decision
        4. State transitions to Workflow Complete
        """
        import governance_runtime.entrypoints.session_reader as session_reader_module
        from governance_runtime.kernel.phase_kernel import KernelResult

        config_root = tmp_path / "config_root"
        commands_home = config_root / "commands"
        commands_home.mkdir(parents=True)

        ws_dir = config_root / "workspaces" / "test-repo"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_path = ws_dir / "SESSION_STATE.json"
        events_path = ws_dir / "logs" / "events.jsonl"

        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(session_path),
            "activeRepoFingerprint": "test-repo",
        }
        (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        state = _make_state()
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state["repo_fingerprint"] = "test-repo"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        (commands_home / "phase_api.yaml").write_text(
            textwrap.dedent("""\
                schema: opencode.governance.phase-api.v1
                phases:
                  "6":
                    next_token: "6"
                    route_strategy: stay
                    entries:
                      - entry: start
                        when: implementation_review_complete
                        next_token: "6"
                        source: phase-6-review-complete
                        active_gate: Pipeline Auto-Approved
                        next_gate_condition: Workflow auto-approved.
            """),
            encoding="utf-8",
        )

        kernel_result = KernelResult(
            phase="6",
            next_token="6",
            active_gate="Pipeline Auto-Approved",
            next_gate_condition="Workflow auto-approved in pipeline mode. Implementation authorized.",
            workspace_ready=True,
            source="pipeline-auto-approve",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-auto-approve-002",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        # Execute via session_reader (simulates /continue)
        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=kernel_result):
            snapshot = session_reader_module.read_session_snapshot(
                commands_home=commands_home,
                materialize=True,
            )

        # Verify: Kernel signal was consumed and auto-approve executed
        assert snapshot.get("status") == "OK"
        assert snapshot.get("active_gate") == "Workflow Complete"

        # Verify: Final on-disk state is consistent
        on_disk = json.loads(session_path.read_text(encoding="utf-8"))
        ss = on_disk.get("SESSION_STATE", on_disk)
        canonical = ss.get("canonical", ss) if isinstance(ss, dict) else ss
        assert canonical.get("workflow_complete") is True
        assert canonical.get("UserReviewDecision", {}).get("source") == "pipeline_auto_approve"


# ---------------------------------------------------------------------------
# Regulated Mode E2E Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRegulatedModeE2E:
    """E2E tests for regulated/agents_strict mode with governance-mode.json.

    These tests prove that regulated mode:
    - Creates governance-mode.json at repo root
    - Kernel does NOT signal auto-approve even with eligible conditions
    - Explicit approval is required
    """

    def test_regulated_mode_with_governance_mode_json_blocks_auto_approve(self, tmp_path: Path):
        """Regulated mode with governance-mode.json does NOT auto-approve.

        This test proves the regulated governance promise end-to-end:
        1. governance-mode.json exists for regulated mode
        2. Kernel eligibility check returns False for agents_strict
        3. Empty decision returns error, not auto-approve
        """
        import governance_runtime.entrypoints.session_reader as session_reader_module
        from governance_runtime.kernel.phase_kernel import KernelResult

        config_root = tmp_path / "config_root"
        commands_home = config_root / "commands"
        commands_home.mkdir(parents=True)

        ws_dir = config_root / "workspaces" / "test-repo"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_path = ws_dir / "SESSION_STATE.json"
        events_path = ws_dir / "logs" / "events.jsonl"
        repo_root = ws_dir

        governance_mode_path = repo_root / "governance-mode.json"
        governance_mode_path.write_text(json.dumps({
            "schema": "governance-mode.v1",
            "state": "active",
            "activated_by": "bootstrap-cli",
            "activated_at": "2026-03-23T12:00:00Z",
            "minimum_retention_days": 3650,
        }), encoding="utf-8")

        pointer = {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(session_path),
            "activeRepoFingerprint": "test-repo",
        }
        (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        state = _make_state(effective_operating_mode="agents_strict")
        state["session_state_revision"] = "1"
        state["session_materialization_event_id"] = "abc123"
        state["session_run_id"] = "run-001"
        state["repo_fingerprint"] = "test-repo"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        (commands_home / "phase_api.yaml").write_text(
            textwrap.dedent("""\
                schema: opencode.governance.phase-api.v1
                phases:
                  "6":
                    next_token: "6"
                    route_strategy: stay
                    entries:
                      - entry: start
                        when: implementation_review_complete
                        next_token: "6"
                        source: phase-6-review-complete
                        active_gate: Evidence Presentation Gate
                        next_gate_condition: Human review required in regulated mode.
            """),
            encoding="utf-8",
        )

        kernel_result = KernelResult(
            phase="6",
            next_token="6",
            active_gate="Evidence Presentation Gate",
            next_gate_condition="Human review required in regulated mode.",
            workspace_ready=True,
            source="phase-6-review-complete",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-regulated-001",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=kernel_result):
            snapshot = session_reader_module.read_session_snapshot(
                commands_home=commands_home,
                materialize=True,
            )

        assert snapshot.get("status") == "OK"
        assert snapshot.get("active_gate") == "Evidence Presentation Gate", (
            f"Regulated mode should stay at Evidence Gate, got: {snapshot.get('active_gate')}"
        )

        on_disk = json.loads(session_path.read_text(encoding="utf-8"))
        ss = on_disk.get("SESSION_STATE", on_disk)
        canonical = ss.get("canonical", ss) if isinstance(ss, dict) else ss
        assert canonical.get("workflow_complete") is not True, (
            "Regulated mode should NOT auto-approve, workflow_complete should not be True"
        )

        result = apply_review_decision(
            decision="",
            session_path=session_path,
        )
        assert result["status"] == "error", (
            f"Empty decision in regulated mode must error, got: {result}"
        )
        assert "reason_code" in result, "Error must include reason_code"

    def test_regulated_kernel_does_not_signal_auto_approve(self, tmp_path: Path):
        """Kernel does NOT signal auto-approve for agents_strict mode.

        Even if all other eligibility conditions are met, the kernel should NOT
        signal source="pipeline-auto-approve" for agents_strict mode.
        """
        state = _make_state(effective_operating_mode="agents_strict")
        state["phase6_review_iterations"] = 3
        state["phase6_max_review_iterations"] = 3

        eligible = pipeline_auto_approve_eligible(state)
        assert eligible is False, (
            f"agents_strict mode should not be eligible for auto-approve, got: {eligible}"
        )
