from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_finalization_record_with_bundle_hash(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-finalization-record",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-finalization-record",
        observed_at="2026-03-11T13:40:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record = json.loads(
        (run_dir(workspaces_home, fingerprint, "run-finalization-record") / "finalization-record.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["schema"] == "governance.finalization-record.v1"
    assert record["artifact_type"] == "finalization_record"
    assert record["run_status"] == "finalized"
    assert record["resolvedOperatingMode"] == "solo"
    assert record["verifyPolicyVersion"] == "v1"
    assert isinstance(record["operatingModeResolution"], dict)
    assert isinstance(record["breakGlass"], dict)
    assert record["bundle_manifest_hash"].startswith("sha256:")
