from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.io_verify import verify_run_archive
from governance_runtime.infrastructure.work_run_archive import archive_active_run, invalidate_archived_run
from governance_runtime.infrastructure.workspace_paths import run_dir


def test_invalidate_archived_run_marks_manifest_and_metadata(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-invalidate",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-invalidate",
        observed_at="2026-03-11T15:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = invalidate_archived_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-invalidate",
        observed_at="2026-03-11T15:01:00Z",
        reason="replaced-by-newer-run",
        superseded=True,
    )
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))

    assert manifest["run_status"] == "invalidated"
    assert manifest["record_status"] == "superseded"
    assert metadata["archive_status"] == "invalidated"
    assert "replaced-by-newer-run" in str(metadata.get("failure_reason", ""))

    ok, _, message = verify_run_archive(run_root)
    assert ok is True, message


def test_invalidate_archived_run_supports_non_superseding_mode(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-invalidate-nosupersede",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-invalidate-nosupersede",
        observed_at="2026-03-11T15:02:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )
    invalidate_archived_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-invalidate-nosupersede",
        observed_at="2026-03-11T15:03:00Z",
        reason="manual-invalidation",
        superseded=False,
    )

    manifest = json.loads(
        (run_dir(workspaces_home, fingerprint, "run-invalidate-nosupersede") / "run-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["record_status"] == "invalidated"
