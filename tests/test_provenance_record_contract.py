from __future__ import annotations

import json
from pathlib import Path

from governance.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_provenance_record_with_required_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-prov",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "SpecHash": "sha256:policy123",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-prov",
        observed_at="2026-03-10T12:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record_path = workspaces_home / "governance-records" / fingerprint / "runs" / "run-prov" / "provenance-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["schema"] == "governance.provenance-record.v1"
    assert record["repo_fingerprint"] == fingerprint
    assert record["run_id"] == "run-prov"
    assert record["trigger"] == "new_work_session_created"
    assert record["policy_fingerprint"] == "sha256:policy123"
    assert record["launcher"] == "governance.entrypoints.new_work_session"
    assert record["timestamps"]["materialized_at"] == "2026-03-10T12:00:00Z"
