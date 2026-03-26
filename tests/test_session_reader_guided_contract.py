from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.entrypoints.session_reader import format_guided_snapshot, main
from tests.util import get_phase_api_path


def test_guided_happy_evidence_presentation_contains_full_review_blocks() -> None:
    snapshot = {
        "status": "OK",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next_gate_condition": "Implementation review loop complete.",
        "review_package_review_object": "Final Phase-6 implementation review decision",
        "review_package_ticket": "Review /review behavior for latest base handling.",
        "review_package_plan_body": "Line 1\nLine 2",
        "review_package_evidence_summary": "plan_record_versions=2",
    }
    action_line = "Next action: run /review-decision <approve|changes_requested|reject>."
    out = format_guided_snapshot(snapshot, action_line)

    assert "Current state" in out
    assert "What this means now" in out
    assert "Presented review content" in out
    assert "PHASE 5 · PLAN FOR APPROVAL" in out
    assert "PLAN (not implemented)" in out
    assert "Approved plan for review:" in out
    assert "Line 1" in out and "Line 2" in out
    assert "/review-decision approve" in out
    assert "/review-decision changes_requested" in out
    assert "/review-decision reject" in out
    assert "  - /plan" not in out
    assert "  - /continue" not in out
    assert out.strip().endswith(action_line)


def test_guided_bad_blocker_contains_blocker_section_and_single_next_action() -> None:
    snapshot = {
        "status": "BLOCKED",
        "phase": "6-PostFlight",
        "active_gate": "Implementation Blocked",
        "next_gate_condition": "Implementation blocked by unresolved critical findings.",
        "gates_blocked": ["P6-Implementation"],
    }
    action_line = "Next action: consult next-step."
    out = format_guided_snapshot(snapshot, action_line)

    assert "Blocker" in out
    assert "P6-Implementation" in out
    assert out.count("Next action:") == 1
    assert "Recovery action:" not in out


def test_guided_corner_implementation_presentation_renders_result_blocks() -> None:
    snapshot = {
        "status": "OK",
        "phase": "6-PostFlight",
        "active_gate": "Implementation Presentation Gate",
        "next_gate_condition": "Implementation package is ready.",
        "implementation_package_review_object": "Implemented result review",
        "implementation_package_plan_reference": "approved plan v2",
        "implementation_package_changed_files": ["src/review.py", "tests/test_review.py"],
        "implementation_package_findings_fixed": ["critical:FIXED-1:resolved"],
        "implementation_package_findings_open": [],
        "implementation_package_checks": ["pytest tests/test_review.py"],
        "implementation_package_stability": "stable",
        "completion_matrix_overall_status": "PASS",
    }
    action_line = "Next action: run /implementation-decision <approve|changes_requested|reject>."
    out = format_guided_snapshot(snapshot, action_line)

    assert "Changed files / artifact summary" in out
    assert "src/review.py" in out
    assert "Findings fixed" in out
    assert "Verification evidence" in out
    assert out.strip().endswith(action_line)


def test_guided_corner_implementation_presentation_routes_to_decision_when_matrix_missing() -> None:
    snapshot = {
        "status": "OK",
        "phase": "6-PostFlight",
        "active_gate": "Implementation Presentation Gate",
        "next_gate_condition": "Implementation package is ready.",
    }
    action_line = "Next action: run /implementation-decision <approve|changes_requested|reject>."
    out = format_guided_snapshot(snapshot, action_line)
    assert out.strip().endswith(action_line)


def test_guided_edge_phase_display_hides_internal_token_labels() -> None:
    snapshot = {
        "status": "OK",
        "phase": "5.4-BusinessRules",
        "active_gate": "Business Rules Validation",
        "next_gate_condition": "Phase 1.5 executed; Phase 5.4 is mandatory before proceeding",
    }
    action_line = "Next action: consult next-step."
    out = format_guided_snapshot(snapshot, action_line)

    assert "- Phase: Phase 5 - Business Rules" in out
    assert "5.4-BusinessRules" not in out


def test_guided_edge_materialize_normal_mode_has_no_yaml_dump(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config_root"
    workspace = config_root / "workspaces" / "fp1"
    commands_home = config_root / "commands"
    workspace.mkdir(parents=True)
    commands_home.mkdir(parents=True)

    pointer = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "fp1",
        "activeSessionStateFile": str(workspace / "SESSION_STATE.json"),
    }
    (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer, ensure_ascii=True), encoding="utf-8")
    (workspace / "SESSION_STATE.json").write_text(
        json.dumps(
            {
                "schema": "opencode-session-state.v1",
                "SESSION_STATE": {
                    "phase": "4",
                    "next": "4",
                    "status": "OK",
                    "active_gate": "Ticket Input Gate",
                    "next_gate_condition": "Provide ticket/task details.",
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    (commands_home / "phase_api.yaml").write_text(
        get_phase_api_path().read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_root / "governance.paths.json").write_text(
        json.dumps(
            {
                "schema": "opencode-governance.paths.v1",
                "paths": {
                    "commandsHome": str(commands_home),
                    "workspacesHome": str(config_root / "workspaces"),
                    "configRoot": str(config_root),
                    "pythonCommand": "python3",
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    rc = main(["--commands-home", str(commands_home), "--materialize"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "active_gate:" not in out
    assert "review_package_plan_body:" not in out
    assert out.count("Next action:") == 1
    assert out.strip().splitlines()[-1].startswith("Next action: ")
