from __future__ import annotations

import json
from pathlib import Path

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

    manifest_path = workspaces_home / "governance-records" / fingerprint / "runs" / "run-lifecycle" / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_status"] == "finalized"
    assert manifest["record_status"] == "finalized"
    assert manifest["finalized_at"] == "2026-03-10T10:10:00Z"
    assert manifest["integrity_status"] == "passed"
