from __future__ import annotations

import hashlib
import json
from pathlib import Path

from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.workspace_paths import run_dir
from governance.infrastructure.work_run_archive import archive_active_run


def _recompute_checksums(run_root: Path) -> None:
    files = {}
    for candidate in sorted(run_root.glob("*.json")):
        if candidate.name == "checksums.json":
            continue
        files[candidate.name] = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
    payload = {"schema": "governance.run-checksums.v1", "files": files}
    (run_root / "checksums.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_verify_rejects_finalized_run_without_finalization_reason(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-meta", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-meta",
        observed_at="2026-03-10T13:30:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = run_dir(workspaces_home, fingerprint, "run-meta")
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    metadata.pop("finalization_reason", None)
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "finalization_reason" in message


def test_verify_rejects_invalid_run_type_and_provenance_launcher(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-prov-contract", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-prov-contract",
        observed_at="2026-03-10T13:35:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = run_dir(workspaces_home, fingerprint, "run-prov-contract")
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["run_type"] = "unknown"
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid run_type" in message

    manifest["run_type"] = "analysis"
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    provenance = json.loads((run_root / "provenance-record.json").read_text(encoding="utf-8"))
    provenance["launcher"] = "other.launcher"
    (run_root / "provenance-record.json").write_text(json.dumps(provenance, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid provenance launcher" in message
