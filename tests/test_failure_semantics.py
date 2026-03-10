from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.infrastructure.work_run_archive import archive_active_run


def test_archive_failure_persists_failed_run_state(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-fail",
        "Phase": "5-ArchitectureReview",
        "active_gate": "Architecture Review Gate",
        "Next": "5.3",
        "plan_record_status": "active",
        "plan_record_versions": 1,
    }

    with pytest.raises(RuntimeError):
        archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=fingerprint,
            run_id="run-fail",
            observed_at="2026-03-10T12:20:00Z",
            session_state_document={"SESSION_STATE": state},
            state_view=state,
        )

    run_root = workspaces_home / "governance-records" / fingerprint / "runs" / "run-fail"
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "failed"
    assert manifest["record_status"] == "invalidated"
    assert metadata["archive_status"] == "failed"
    assert isinstance(metadata["failure_reason"], str)
