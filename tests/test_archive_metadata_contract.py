from __future__ import annotations

import json
from pathlib import Path

from governance.infrastructure.workspace_paths import run_dir
from governance.infrastructure.work_run_archive import archive_active_run


def test_archive_metadata_tracks_materialization_and_finalization(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-meta",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-meta",
        observed_at="2026-03-10T12:40:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    metadata = json.loads((run_dir(workspaces_home, fingerprint, "run-meta") / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["archive_status"] == "finalized"
    assert metadata["finalization_reason"] == "all-required-artifacts-present-and-verified"
    assert metadata["archived_files"]["run_manifest"] is True
    assert metadata["archived_files"]["provenance_record"] is True
    assert metadata["archived_files"]["checksums"] is True
