from __future__ import annotations

import json
from pathlib import Path

from governance.infrastructure.work_run_archive import archive_active_run


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_archive_writes_repository_and_run_manifest(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    workspace = workspaces_home / fingerprint
    workspace.mkdir(parents=True)

    document = {"SESSION_STATE": {"session_run_id": "run-1", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}}
    result = archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-1",
        observed_at="2026-03-10T10:00:00Z",
        session_state_document=document,
        state_view=document["SESSION_STATE"],
    )

    assert result.run_id == "run-1"
    repository_manifest = json.loads((workspace / "runs" / "repository-manifest.json").read_text(encoding="utf-8"))
    assert repository_manifest["schema"] == "governance.repository-manifest.v1"

    run_manifest = json.loads((workspace / "runs" / "run-1" / "run-manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["schema"] == "governance.run-manifest.v1"
    assert run_manifest["run_id"] == "run-1"
    assert run_manifest["required_artifacts"]["session_state"] is True
    assert run_manifest["required_artifacts"]["checksums"] is True


def test_repository_manifest_is_stable_across_multiple_archives(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-1", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-1",
        observed_at="2026-03-10T12:45:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )
    manifest_path = workspaces_home / fingerprint / "runs" / "repository-manifest.json"
    first_manifest = manifest_path.read_text(encoding="utf-8")

    state2 = {"session_run_id": "run-2", "Phase": "4", "active_gate": "Ticket Input Gate", "Next": "5"}
    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-2",
        observed_at="2026-03-10T12:50:00Z",
        session_state_document={"SESSION_STATE": state2},
        state_view=state2,
    )
    second_manifest = manifest_path.read_text(encoding="utf-8")

    assert first_manifest == second_manifest
