from __future__ import annotations

import hashlib
import json
from pathlib import Path

from governance.infrastructure.io_verify import verify_repository_manifest, verify_run_archive
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


def test_verify_rejects_invalid_manifest_metadata_provenance_schema(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-schema", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-schema",
        observed_at="2026-03-10T13:50:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-schema"

    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["schema"] = "governance.run-manifest.v0"
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)
    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid run-manifest schema" in message

    manifest["schema"] = "governance.run-manifest.v1"
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    metadata["schema"] = "governance.work-run.snapshot.v1"
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)
    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid metadata schema" in message

    metadata["schema"] = "governance.work-run.snapshot.v2"
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    provenance = json.loads((run_root / "provenance-record.json").read_text(encoding="utf-8"))
    provenance["schema"] = "governance.provenance-record.v0"
    (run_root / "provenance-record.json").write_text(json.dumps(provenance, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)
    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid provenance schema" in message


def test_verify_rejects_malformed_archive_json_payloads(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-malformed", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-malformed",
        observed_at="2026-03-10T13:55:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-malformed"

    (run_root / "checksums.json").write_text("{", encoding="utf-8")
    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Failed to parse checksums.json" in message


def test_verify_repository_manifest_contract(tmp_path: Path) -> None:
    runs_root = tmp_path / "workspaces" / "abc123def456abc123def456" / "runs"
    runs_root.mkdir(parents=True)

    ok, message = verify_repository_manifest(runs_root, expected_repo_fingerprint="abc123def456abc123def456")
    assert ok is False
    assert isinstance(message, str)
    assert "Missing repository manifest" in message

    manifest = {
        "schema": "governance.repository-manifest.v1",
        "repo_fingerprint": "abc123def456abc123def456",
        "created_at": "2026-03-10T14:00:00Z",
        "storage_topology": {
            "runtime_root": "workspaces/<fingerprint>",
            "audit_runs_root": "workspaces/<fingerprint>/runs",
        },
    }
    (runs_root / "repository-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")

    ok, message = verify_repository_manifest(runs_root, expected_repo_fingerprint="abc123def456abc123def456")
    assert ok is True
    assert message is None

    manifest["storage_topology"]["audit_runs_root"] = "workspaces/<fingerprint>/archives"
    (runs_root / "repository-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    ok, message = verify_repository_manifest(runs_root, expected_repo_fingerprint="abc123def456abc123def456")
    assert ok is False
    assert isinstance(message, str)
    assert "Invalid audit_runs_root" in message


def test_verify_rejects_required_artifacts_key_and_run_type_mismatch(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-artifacts", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-artifacts",
        observed_at="2026-03-10T14:05:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-artifacts"
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    required = manifest["required_artifacts"]
    assert isinstance(required, dict)

    required.pop("provenance", None)
    manifest["required_artifacts"] = required
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "required_artifacts key mismatch" in message

    required["provenance"] = True
    manifest["required_artifacts"] = required
    manifest["run_type"] = "analysis"
    required["plan_record"] = True
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "analysis run_type requires" in message


def test_verify_rejects_failed_run_without_failure_reason(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-failure-reason", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-failure-reason",
        observed_at="2026-03-10T14:20:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-failure-reason"
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))

    manifest["run_status"] = "failed"
    manifest["record_status"] = "invalidated"
    manifest["integrity_status"] = "failed"
    manifest["finalized_at"] = None
    metadata["archive_status"] = "failed"
    metadata.pop("failure_reason", None)

    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "failure_reason" in message


def test_verify_rejects_materialized_run_with_non_pending_integrity(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-materialized", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-materialized",
        observed_at="2026-03-10T14:40:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-materialized"
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["run_status"] = "materialized"
    manifest["integrity_status"] = "passed"
    manifest["finalized_at"] = None
    manifest["record_status"] = "draft"
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Materialized run must have integrity_status=pending" in message


def test_verify_rejects_materialized_timestamp_mismatch(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-ts", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-ts",
        observed_at="2026-03-10T14:30:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-ts"
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["materialized_at"] = "2026-03-10T14:31:00Z"
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "materialized_at/archived_at mismatch" in message
