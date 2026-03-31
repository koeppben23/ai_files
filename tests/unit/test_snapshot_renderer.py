"""Tests for snapshot renderer module."""

from __future__ import annotations

import pytest

from governance_runtime.application.dto.session_state_types import Snapshot
from governance_runtime.infrastructure.rendering.snapshot_renderer import (
    SNAPSHOT_SCHEMA,
    _display_phase,
    _has_blocker,
    _render_blocker,
    _render_current_state,
    _render_execution_progress,
    _render_presented_review_content,
    _render_phase5_decision_brief_from_plan_body,
    _build_plan_under_review_lines,
    _sanitize_phase5_decision_brief,
    _section,
    format_standard_snapshot,
    format_snapshot,
    format_guided_snapshot,
)


def _to_snapshot(d: dict) -> Snapshot:
    """Helper to cast dict to Snapshot TypedDict for testing."""
    return d  # type: ignore[return-value]


class TestDisplayPhase:
    """Tests for _display_phase."""

    def test_phase_4(self):
        assert _display_phase("4") == "Phase 4 - Ticket Intake"

    def test_phase_5(self):
        assert _display_phase("5") == "Phase 5 - Architecture Review"

    def test_phase_54(self):
        assert _display_phase("5.4") == "Phase 5 - Business Rules"

    def test_phase_55(self):
        assert _display_phase("5.5") == "Phase 5 - Technical Debt"

    def test_phase_56(self):
        assert _display_phase("5.6") == "Phase 5 - Rollback Safety"

    def test_phase_6(self):
        assert _display_phase("6") == "Phase 6 - Post Flight"

    def test_phase_1(self):
        assert _display_phase("1") == "Phase 1 - Bootstrap"

    def test_empty(self):
        assert _display_phase("") == "unknown"

    def test_none(self):
        assert _display_phase(None) == "unknown"


class TestSection:
    """Tests for _section."""

    def test_adds_title(self):
        lines = []
        _section(lines, "Test Section")
        assert lines == ["Test Section"]

    def test_adds_blank_line_before_when_lines_exist(self):
        lines = ["Previous content"]
        _section(lines, "New Section")
        assert lines == ["Previous content", "", "New Section"]


class TestRenderCurrentState:
    """Tests for _render_current_state."""

    def test_renders_state(self):
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Implementation Internal Review",
        })
        lines = _render_current_state(snapshot)
        assert lines[0] == "Current state"
        assert "Phase 6 - Post Flight" in lines[1]
        assert "Implementation Internal Review" in lines[2]


class TestRenderExecutionProgress:
    """Tests for _render_execution_progress."""

    def test_renders_review_loop(self):
        snapshot = _to_snapshot({
            "active_gate": "Implementation Internal Review",
            "phase6_review_iterations": 2,
            "phase6_max_review_iterations": 3,
            "phase6_revision_delta": "changed",
        })
        lines = _render_execution_progress(snapshot)
        assert "Execution progress" in lines[0]
        assert "iteration=2/3" in lines[1]

    def test_renders_business_rules(self):
        snapshot = _to_snapshot({
            "active_gate": "Business Rules Validation",
            "p54_evaluated_status": "compliant",
            "p54_invalid_rules": 0,
            "p54_dropped_candidates": 0,
            "p54_code_candidate_count": 5,
            "p54_code_surface_count": 10,
        })
        lines = _render_execution_progress(snapshot)
        assert "COMPLIANT" in lines[1]


class TestHasBlocker:
    """Tests for _has_blocker."""

    def test_true_when_error_status(self):
        snapshot = _to_snapshot({"status": "error"})
        assert _has_blocker(snapshot) is True

    def test_true_when_blocked_status(self):
        snapshot = _to_snapshot({"status": "blocked"})
        assert _has_blocker(snapshot) is True

    def test_true_when_gates_blocked(self):
        snapshot = _to_snapshot({"gates_blocked": ["P5.4-BusinessRules"]})
        assert _has_blocker(snapshot) is True

    def test_false_when_ok(self):
        snapshot = _to_snapshot({"status": "OK"})
        assert _has_blocker(snapshot) is False


class TestFormatSnapshot:
    """Tests for format_snapshot."""

    def test_includes_schema(self):
        snapshot = _to_snapshot({"status": "OK"})
        output = format_snapshot(snapshot)
        assert f"# {SNAPSHOT_SCHEMA}" in output

    def test_excludes_schema_key(self):
        snapshot = _to_snapshot({"schema": "test", "status": "OK"})
        output = format_snapshot(snapshot)
        lines = output.strip().split("\n")
        assert lines[0].startswith("# ")
        assert not any("schema:" in line for line in lines[1:])

    def test_formats_list_values(self):
        snapshot = _to_snapshot({"items": ["a", "b", "c"]})
        output = format_snapshot(snapshot)
        assert "items:" in output


class TestFormatGuidedSnapshot:
    """Tests for format_guided_snapshot."""

    def test_includes_current_state(self):
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Implementation Internal Review",
            "next_gate_condition": "Complete review",
        })
        output = format_guided_snapshot(snapshot, "Next action: run /continue.")
        assert "Current state" in output
        assert "Phase 6 - Post Flight" in output

    def test_includes_blocker_section(self):
        snapshot = _to_snapshot({
            "status": "blocked",
            "phase": "5.4",
            "active_gate": "Business Rules Validation",
            "next_gate_condition": "Blocked by rule violations",
            "p54_evaluated_status": "failed",
        })
        output = format_guided_snapshot(snapshot, "Next action: resolve blocker.")
        assert "Blocker" in output

    def test_includes_review_content(self):
        snapshot = _to_snapshot({
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "review_package_review_object": "Test Review",
            "review_package_ticket": "TICKET-1",
            "review_package_plan_body": "# PHASE 5 · PLAN FOR APPROVAL\nPlan body text",
            "review_package_approved_plan_summary": "Implement the approved plan in service layer.",
            "review_package_evidence_summary": "All evidence present",
            "next_gate_condition": "Present the package and submit a decision.",
        })
        output = format_guided_snapshot(snapshot, "Next action: run /review-decision.")
        assert "Current state" not in output
        assert "What this means now" not in output
        assert "Plan under review" in output
        assert "Implement the approved plan in service layer." in output
        assert output.strip().endswith("Next action: run /review-decision.")

    def test_includes_execution_progress(self):
        snapshot = _to_snapshot({
            "active_gate": "Implementation Internal Review",
            "phase6_review_iterations": 1,
            "phase6_max_review_iterations": 3,
            "phase6_revision_delta": "changed",
        })
        output = format_guided_snapshot(snapshot, "Next action: run /continue.")
        assert "Execution progress" in output
        assert "iteration=1/3" in output

    def test_verbose_governance_frame_keeps_wrapper_sections(self):
        snapshot = _to_snapshot({
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "next_gate_condition": "Implementation review loop complete.",
            "review_package_plan_body": "# PHASE 5 · PLAN FOR APPROVAL\nPlan body text",
        })
        output = format_guided_snapshot(
            snapshot,
            "Next action: run /review-decision.",
            verbose_governance_frame=True,
        )
        assert "Current state" in output
        assert "Presented review content" in output
        assert "Next action: run /review-decision." in output


class TestFormatStandardSnapshot:
    """Tests for format_standard_snapshot."""

    def test_includes_plan_under_review_when_snapshot_has_plan_data(self):
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Some Other Gate",
            "next_gate_condition": "Continue review.",
            "review_package_approved_plan_summary": "Use canary rollout for deployment.",
        })

        output = format_standard_snapshot(snapshot, "Next action: run /continue.")

        assert "Current phase is 6 with active gate Some Other Gate." in output
        assert "Current next is: Continue review." in output
        assert "Plan under review: Use canary rollout for deployment." in output
        assert output.strip().endswith("Next action: run /continue.")

    def test_omits_plan_under_review_when_no_plan_data(self):
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Evidence Presentation Gate",
            "next_gate_condition": "Continue review.",
        })

        output = format_standard_snapshot(snapshot, "Next action: run /continue.")

        assert "Plan under review:" not in output
        assert output.strip().endswith("Next action: run /continue.")

    def test_omits_plan_under_review_when_blocked(self):
        snapshot = _to_snapshot({
            "status": "blocked",
            "phase": "6",
            "active_gate": "Implementation Presentation Gate",
            "next_gate_condition": "Address blocker.",
            "review_package_plan_body": "# Plan\n\n- Step 1",
        })

        output = format_standard_snapshot(snapshot, "Next action: resolve blocker.")

        assert "Plan under review:" not in output
        assert "Current blocker is active:" in output
        assert output.strip().endswith("Next action: resolve blocker.")

    def test_falls_back_to_plan_body_when_summary_missing(self):
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Architecture Review Gate",
            "next_gate_condition": "Continue review.",
            "review_package_plan_body": "# Plan\n\n- Step 1\n- Step 2\n",
        })

        output = format_standard_snapshot(snapshot, "Next action: run /continue.")

        assert "Plan under review:" in output
        assert "Plan; - Step 1; - Step 2" in output

    def test_truncation_is_deterministic_in_standard_output(self):
        long_summary = "A" * 900
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Any Gate",
            "next_gate_condition": "Continue review.",
            "review_package_approved_plan_summary": long_summary,
        })

        output1 = format_standard_snapshot(snapshot, "Next action: run /continue.")
        output2 = format_standard_snapshot(snapshot, "Next action: run /continue.")

        assert output1 == output2
        assert "Plan under review:" in output1
        assert "..." in output1

        plan_line = [line for line in output1.splitlines() if line.startswith("Plan under review:")][0]
        assert len(plan_line) <= 850

    def test_standard_and_debug_share_plan_content_for_same_snapshot(self):
        snapshot = _to_snapshot({
            "phase": "6",
            "active_gate": "Evidence Presentation Gate",
            "next_gate_condition": "Present and decide.",
            "review_package_approved_plan_summary": "Ship canary rollout first.",
        })

        standard_output = format_standard_snapshot(snapshot, "Next action: run /review-decision.")
        debug_output = format_guided_snapshot(snapshot, "Next action: run /review-decision.")

        assert "Plan under review: Ship canary rollout first." in standard_output
        assert "Plan under review" in debug_output
        assert "- Ship canary rollout first." in debug_output

    def test_standard_alias_is_narrative_compatible(self):
        snapshot = _to_snapshot({
            "phase": "4",
            "active_gate": "Ticket Input Gate",
            "next_gate_condition": "Provide task details",
        })

        output = format_standard_snapshot(snapshot, "Next action: run /ticket.")

        assert "Current phase is 4 with active gate Ticket Input Gate." in output
        assert "Current next is: Provide task details." in output


class TestDecisionBriefSanitizer:
    def test_rewrites_signal_diagnostics_and_python_lists(self):
        body = (
            "## Executive Summary\n"
            "- Objective signal: foo, bar.\n"
            "- Target-state signal: no clear signal captured.\n"
            "- Go/No-Go signal: no clear signal captured.\n\n"
            "## Risks & Mitigations\n"
            "- ['Risk A', 'Risk B']\n\n"
            "## Technical Appendix\n\n"
            "### Plan Objective\n"
            "Deliver pipeline mode e2e coverage.\n"
        )
        out = _sanitize_phase5_decision_brief(body)
        assert "Objective signal:" not in out
        assert "Target-state signal:" not in out
        assert "Go/No-Go signal:" not in out
        assert "- Objective: Deliver pipeline mode e2e coverage." in out
        assert "- Risk A" in out
        assert "- Risk B" in out


class TestPlanUnderReviewBlock:
    def test_happy_uses_summary_when_present(self):
        snapshot = _to_snapshot({
            "review_package_approved_plan_summary": "Line A\nLine B",
            "review_package_plan_body": "# Fallback\nLine C",
        })
        lines = _build_plan_under_review_lines(snapshot)
        assert lines == ["Line A", "Line B"]

    def test_bad_returns_empty_when_no_plan_data(self):
        snapshot = _to_snapshot({})
        assert _build_plan_under_review_lines(snapshot) == []

    def test_corner_falls_back_to_plan_body_when_summary_missing(self):
        snapshot = _to_snapshot({
            "review_package_plan_body": "# Title\n\n- Item 1\n- Item 2\n",
        })
        lines = _build_plan_under_review_lines(snapshot)
        assert lines == ["Title", "- Item 1", "- Item 2"]

    def test_edge_truncates_to_800_char_budget(self):
        long_line = "A" * 1200
        snapshot = _to_snapshot({"review_package_approved_plan_summary": long_line})
        lines = _build_plan_under_review_lines(snapshot)
        assert lines
        combined = "\n".join(lines)
        assert len(combined) <= 800
        assert combined.endswith("...")


def test_decision_brief_renderer_uses_template(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (
        "# PHASE 5 · PLAN FOR APPROVAL\n"
        "PLAN (not implemented)\n\n"
        "## Decision Required\n"
        "Decision required: choose approve, changes_requested, or reject.\n\n"
        "## Executive Summary\n"
        "- Summary line\n\n"
        "## Scope\n"
        "Scope line\n\n"
        "## Release Gates\n"
        "Gate line\n\n"
        "## Next Actions\n"
        "- /review-decision approve\n"
    )
    monkeypatch.setattr(
        "governance_runtime.infrastructure.rendering.snapshot_renderer._load_phase5_decision_brief_template",
        lambda: "# CUSTOM\n{title}\n{decision_required}\n",
    )
    rendered = _render_phase5_decision_brief_from_plan_body(body)
    assert rendered.startswith("# CUSTOM")
    assert "PHASE 5 · PLAN FOR APPROVAL" in rendered


class TestRenderBlocker:
    """Tests for _render_blocker."""

    def test_basic_blocker(self):
        snapshot = _to_snapshot({
            "status": "blocked",
            "next_gate_condition": "Test blocker condition",
        })
        lines = _render_blocker(snapshot)
        assert lines[0] == "Blocker"
        assert "blocked" in lines[1]
        assert "Test blocker condition" in lines[2]

    def test_p54_blocker_details(self):
        snapshot = _to_snapshot({
            "status": "blocked",
            "phase": "5.4-BusinessRules",
            "next_gate_condition": "Business rules not compliant",
            "p54_evaluated_status": "failed",
            "p54_invalid_rules": 5,
            "p54_dropped_candidates": 2,
            "p54_reason_code": "RULES_NOT_COMPLIANT",
            "p54_has_code_extraction": True,
            "p54_code_coverage_sufficient": False,
            "p54_code_candidate_count": 10,
            "p54_code_surface_count": 20,
        })
        lines = _render_blocker(snapshot)
        assert "Business Rules Validation: FAILED" in "".join(lines)
        assert "Invalid rules detected: 5" in "".join(lines)
