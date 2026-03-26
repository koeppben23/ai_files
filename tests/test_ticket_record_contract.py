from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_ticket_record_with_contract_header(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-ticket",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
        "ticket_ref": "T-123",
        "ticket_title": "Contract hardening",
        "TicketRecordDigest": "sha256:ticket123",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-ticket",
        observed_at="2026-03-11T13:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record = json.loads((run_dir(workspaces_home, fingerprint, "run-ticket") / "ticket-record.json").read_text(encoding="utf-8"))
    assert record["schema"] == "governance.ticket-record.v1"
    assert record["artifact_type"] == "ticket_record"
    assert record["run_id"] == "run-ticket"
    assert record["ticket_ref"] == "T-123"
