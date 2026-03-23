"""Tests for Pipeline Auto-Approve feature.

Tests cover:
- Pipeline auto-approve eligibility check
- Pipeline auto-approve application
- Blocking in non-pipeline modes (user, agents_strict)
- Audit trail creation

Happy / Negative / Corner / Edge coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_runtime.entrypoints.pipeline_auto_approve import (
    apply_pipeline_auto_approve,
    pipeline_auto_approve_eligible,
)


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
    """Tests for pipeline_auto_approve_eligible() function."""

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
# Apply Pipeline Auto-Approve Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestApplyPipelineAutoApprove:
    """Tests for apply_pipeline_auto_approve() function."""

    def test_apply_creates_workflow_complete(self, tmp_path: Path):
        """Applying auto-approve sets workflow_complete=True."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_pipeline_auto_approve(session_path=session_path)

        assert result["status"] == "ok"
        updated = json.loads(session_path.read_text(encoding="utf-8"))
        assert updated["SESSION_STATE"]["workflow_complete"] is True
        assert updated["SESSION_STATE"]["implementation_authorized"] is True

    def test_apply_records_auto_approve_source(self, tmp_path: Path):
        """Auto-approve decision records source=pipeline_auto_approve."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        apply_pipeline_auto_approve(session_path=session_path)

        updated = json.loads(session_path.read_text(encoding="utf-8"))
        decision = updated["SESSION_STATE"]["UserReviewDecision"]
        assert decision["source"] == "pipeline_auto_approve"
        assert decision["decision"] == "approve"

    def test_apply_writes_audit_event(self, tmp_path: Path):
        """Auto-approve writes audit event to events_path."""
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        state = _make_state()
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        apply_pipeline_auto_approve(session_path=session_path, events_path=events_path)

        assert events_path.exists()
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event"] == "pipeline_auto_approve"
        assert event["mode"] == "pipeline"
        assert event["result"] == "approved"

    def test_apply_blocks_when_not_eligible(self, tmp_path: Path):
        """Applying auto-approve is blocked when not eligible."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="user")
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_pipeline_auto_approve(session_path=session_path)

        assert result["status"] == "blocked"
        assert "reason_code" in result

    def test_apply_blocks_in_agents_strict_mode(self, tmp_path: Path):
        """Auto-approve is blocked in agents_strict (regulated) mode."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state(effective_operating_mode="agents_strict")
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_pipeline_auto_approve(session_path=session_path)

        assert result["status"] == "blocked"

    def test_apply_returns_error_when_session_not_found(self, tmp_path: Path):
        """Returns error when session state file does not exist."""
        session_path = tmp_path / "nonexistent" / "SESSION_STATE.json"

        result = apply_pipeline_auto_approve(session_path=session_path)

        assert result["status"] == "error"
        assert "not found" in result["message"]


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
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_pipeline_auto_approve(session_path=session_path)
        assert result["status"] == "ok"

    def test_preserves_existing_state_fields(self, tmp_path: Path):
        """Applying auto-approve preserves other state fields."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        state["some_other_field"] = "preserved"
        state["PlanRecordDigest"] = "abc123"
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        apply_pipeline_auto_approve(session_path=session_path)

        updated = json.loads(session_path.read_text(encoding="utf-8"))
        assert updated["SESSION_STATE"]["some_other_field"] == "preserved"
        assert updated["SESSION_STATE"]["PlanRecordDigest"] == "abc123"

    def test_apply_without_events_path_succeeds(self, tmp_path: Path):
        """Auto-approve succeeds even without events_path."""
        session_path = tmp_path / "SESSION_STATE.json"
        state = _make_state()
        session_path.write_text(json.dumps({"SESSION_STATE": state}), encoding="utf-8")

        result = apply_pipeline_auto_approve(session_path=session_path, events_path=None)

        assert result["status"] == "ok"
