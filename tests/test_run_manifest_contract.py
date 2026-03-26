from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_pr_run_manifest_requires_pr_record_and_finalizer_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-manifest-pr",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
        "PullRequestTitle": "feat: demo",
        "PullRequestBody": "body",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-manifest-pr",
        observed_at="2026-03-11T13:04:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    manifest = json.loads((run_dir(workspaces_home, fingerprint, "run-manifest-pr") / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "governance.run-manifest.v1"
    assert manifest["run_type"] == "pr"
    assert manifest["required_artifacts"]["pr_record"] is True
    assert manifest["required_artifacts"]["plan_record"] is False
    assert manifest["run_status"] == "finalized"
    assert manifest["finalized_by"] == "governance.finalizer"
