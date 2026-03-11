from __future__ import annotations

import json
from pathlib import Path

from governance.infrastructure.workspace_paths import run_dir
from governance.infrastructure.work_run_archive import archive_active_run


def test_run_manifest_contains_lifecycle_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-lifecycle", "Phase": "5-ArchitectureReview", "active_gate": "Architecture Review Gate", "Next": "5.3"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-lifecycle",
        observed_at="2026-03-10T10:10:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    manifest_path = run_dir(workspaces_home, fingerprint, "run-lifecycle") / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_status"] == "finalized"
    assert manifest["record_status"] == "finalized"
    assert manifest["finalized_at"] == "2026-03-10T10:10:00Z"
    assert manifest["integrity_status"] == "passed"
    assert manifest["resolvedOperatingMode"] == "solo"
    assert manifest["verifyPolicyVersion"] == "v1"
    assert isinstance(manifest["operatingModeResolution"], dict)
    assert isinstance(manifest["breakGlass"], dict)


def test_regulated_mode_blocks_pr_finalization_without_approval(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-regulated-pr",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "PullRequestTitle": "feat: guarded export",
        "PullRequestBody": "body",
        "regulated_mode_state": "active",
        "requires_human_approval": True,
        "approval_status": "pending",
    }

    try:
        archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=fingerprint,
            run_id="run-regulated-pr",
            observed_at="2026-03-10T10:20:00Z",
            session_state_document={"SESSION_STATE": state},
            state_view=state,
        )
    except Exception:
        pass

    manifest_path = run_dir(workspaces_home, fingerprint, "run-regulated-pr") / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_status"] == "failed"
    errors = manifest.get("finalization_errors")
    assert isinstance(errors, list)
    assert any("requires approved human approval" in str(item) for item in errors)


def test_regulated_mode_blocks_pr_finalization_with_non_independent_approver(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-regulated-same-approver",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "PullRequestTitle": "feat: guarded export",
        "PullRequestBody": "body",
        "regulated_mode_state": "active",
        "requires_human_approval": True,
        "approval_status": "approved",
        "role": "operator",
        "approver_role": "operator",
    }

    try:
        archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=fingerprint,
            run_id="run-regulated-same-approver",
            observed_at="2026-03-11T10:20:00Z",
            session_state_document={"SESSION_STATE": state},
            state_view=state,
        )
    except Exception:
        pass

    manifest_path = run_dir(workspaces_home, fingerprint, "run-regulated-same-approver") / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_status"] == "failed"
    errors = manifest.get("finalization_errors")
    assert isinstance(errors, list)
    assert any("four-eyes" in str(item) for item in errors)


def test_regulated_mode_allows_pr_finalization_with_independent_approver(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-regulated-approved",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "PullRequestTitle": "feat: guarded export",
        "PullRequestBody": "body",
        "regulated_mode_state": "active",
        "requires_human_approval": True,
        "approval_status": "approved",
        "role": "operator",
        "approver_role": "approver",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-regulated-approved",
        observed_at="2026-03-11T10:21:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    manifest_path = run_dir(workspaces_home, fingerprint, "run-regulated-approved") / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_status"] == "finalized"
