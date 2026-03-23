from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_outcome_record_with_phase_surface(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-outcome",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "result": "success",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-outcome",
        observed_at="2026-03-11T13:02:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record = json.loads((run_dir(workspaces_home, fingerprint, "run-outcome") / "outcome-record.json").read_text(encoding="utf-8"))
    assert record["schema"] == "governance.outcome-record.v1"
    assert record["result"] == "success"
    assert record["phase"] == "6-PostFlight"
    assert record["active_gate"] == "Evidence Presentation Gate"
