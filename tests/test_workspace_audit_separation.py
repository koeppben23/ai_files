from __future__ import annotations

import json
from pathlib import Path

from governance.infrastructure.run_audit_artifacts import purge_runtime_artifacts
from governance.infrastructure.work_run_archive import archive_active_run


def test_runtime_purge_does_not_touch_audit_runs(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    workspace = workspaces_home / fingerprint
    workspace.mkdir(parents=True)

    state = {"session_run_id": "run-sep", "Phase": "4", "active_gate": "Ticket Input Gate", "Next": "5"}
    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-sep",
        observed_at="2026-03-10T10:40:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    (workspace / "SESSION_STATE.json").write_text(json.dumps({"SESSION_STATE": state}, ensure_ascii=True), encoding="utf-8")
    (workspace / "events.jsonl").write_text("{}\n", encoding="utf-8")
    assert (workspaces_home / "governance-records" / fingerprint / "runs" / "run-sep" / "run-manifest.json").is_file()

    removed = purge_runtime_artifacts(workspace)
    assert "SESSION_STATE.json" in removed
    assert "events.jsonl" not in removed
    assert (workspaces_home / "governance-records" / fingerprint / "runs" / "run-sep" / "run-manifest.json").is_file()
