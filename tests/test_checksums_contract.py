from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.io_verify import verify_run_archive
from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_checksums_cover_required_materialized_artifacts(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-checksum-contract",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-checksum-contract",
        observed_at="2026-03-11T13:06:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    checksums = json.loads((run_dir(workspaces_home, fingerprint, "run-checksum-contract") / "checksums.json").read_text(encoding="utf-8"))
    files = checksums["files"]
    assert "SESSION_STATE.json" in files
    assert "run-manifest.json" in files
    assert "provenance-record.json" in files
    assert all(str(value).startswith("sha256:") for value in files.values())


def test_verify_fails_on_tampered_artifact_content(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-checksum-tamper",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-checksum-tamper",
        observed_at="2026-03-11T13:07:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = run_dir(workspaces_home, fingerprint, "run-checksum-tamper")
    outcome_path = run_root / "outcome-record.json"
    payload = json.loads(outcome_path.read_text(encoding="utf-8"))
    payload["result"] = "tampered"
    outcome_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Checksum mismatch: outcome-record.json" in message
