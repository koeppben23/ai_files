from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_review_decision_record_with_decision_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-review-decision",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
        "review_decision": "approve",
        "review_decision_note": "looks good",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-review-decision",
        observed_at="2026-03-11T13:01:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record = json.loads(
        (run_dir(workspaces_home, fingerprint, "run-review-decision") / "review-decision-record.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["schema"] == "governance.review-decision-record.v1"
    assert record["artifact_type"] == "review_decision_record"
    assert record["decision"] == "approve"
    assert record["decision_note"] == "looks good"
