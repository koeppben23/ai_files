from __future__ import annotations

from pathlib import Path

import pytest

from governance.infrastructure.work_run_archive import archive_active_run


def test_pr_record_required_only_for_pr_runs(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"

    plan_state = {"session_run_id": "run-plan", "Phase": "5-ArchitectureReview", "active_gate": "Architecture Review Gate", "Next": "5.3"}
    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-plan",
        observed_at="2026-03-10T10:20:00Z",
        session_state_document={"SESSION_STATE": plan_state},
        state_view=plan_state,
    )
    assert not (workspaces_home / fingerprint / "runs" / "run-plan" / "pr-record.json").exists()

    pr_state = {
        "session_run_id": "run-pr",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "PullRequestTitle": "feat: add audit contract",
        "PullRequestBody": "## Summary\n- Added records",
    }
    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-pr",
        observed_at="2026-03-10T10:21:00Z",
        session_state_document={"SESSION_STATE": pr_state},
        state_view=pr_state,
    )
    assert (workspaces_home / fingerprint / "runs" / "run-pr" / "pr-record.json").is_file()


def test_plan_run_requires_plan_record_for_finalization(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    plan_state = {
        "session_run_id": "run-plan-required",
        "Phase": "5-ArchitectureReview",
        "active_gate": "Architecture Review Gate",
        "Next": "5.3",
        "plan_record_status": "active",
        "plan_record_versions": 2,
    }

    with pytest.raises(RuntimeError):
        archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=fingerprint,
            run_id="run-plan-required",
            observed_at="2026-03-10T10:22:00Z",
            session_state_document={"SESSION_STATE": plan_state},
            state_view=plan_state,
        )
