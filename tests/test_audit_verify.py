from __future__ import annotations

import hashlib
import json
from pathlib import Path

from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.work_run_archive import archive_active_run


def _recompute_checksums(run_root: Path) -> None:
    files = {}
    for name in [
        "SESSION_STATE.json",
        "metadata.json",
        "run-manifest.json",
        "provenance-record.json",
    ]:
        files[name] = "sha256:" + hashlib.sha256((run_root / name).read_bytes()).hexdigest()
    payload = {"schema": "governance.run-checksums.v1", "files": files}
    (run_root / "checksums.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_verify_detects_tamper_and_incomplete_runs(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-verify", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-verify",
        observed_at="2026-03-10T10:30:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-verify"
    ok, _, message = verify_run_archive(run_root)
    assert ok is True
    assert message is None

    (run_root / "SESSION_STATE.json").write_text('{"tampered":true}', encoding="utf-8")
    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Checksum mismatch" in message

    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["run_status"] = "finalized"
    manifest["integrity_status"] = "failed"
    manifest["finalized_at"] = ""
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "integrity_status=passed" in message


def test_verify_detects_run_id_and_fingerprint_mismatch(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-ids", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-ids",
        observed_at="2026-03-10T13:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-ids"
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    metadata["run_id"] = "other-run"
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "run_id mismatch" in message

    metadata["run_id"] = "run-ids"
    metadata["repo_fingerprint"] = "ffffffffffffffffffffffff"
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "repo_fingerprint mismatch" in message


def test_verify_rejects_invalid_checksums_schema(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-checksum-schema", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-checksum-schema",
        observed_at="2026-03-10T13:45:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-checksum-schema"
    checksums = json.loads((run_root / "checksums.json").read_text(encoding="utf-8"))
    checksums["schema"] = "governance.run-checksums.v0"
    (run_root / "checksums.json").write_text(json.dumps(checksums, ensure_ascii=True), encoding="utf-8")

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid checksums schema" in message
