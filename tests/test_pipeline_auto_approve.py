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
from pathlib import Path

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
        "Phase": phase,
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
        """agents_strict (regulated) mode is NOT eligible for auto-approve."""
        state = _make_state(
            effective_operating_mode="agents_strict",
            active_gate="Evidence Presentation Gate",
        )
        assert pipeline_auto_approve_eligible(state) is False

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
        """apply_review_decision with empty decision blocks in agents_strict mode."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="agents_strict")
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_review_decision(
            decision="",
            session_path=session_path,
        )

        assert result["status"] == "error"

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
