import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def verify_pointer(pointer_path: Path, expected_fingerprint: str) -> Tuple[bool, Optional[str]]:
    if not pointer_path.is_file():
        return False, f"Path is not a file: {pointer_path}"

    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Failed to read pointer: {e}"

    schema = data.get("schema")
    if schema != "opencode-session-pointer.v1":
        return False, f"Schema mismatch: expected opencode-session-pointer.v1, got {schema}"

    fingerprint = data.get("activeRepoFingerprint")
    if not isinstance(fingerprint, str) or fingerprint != expected_fingerprint:
        return False, f"Fingerprint mismatch: expected {expected_fingerprint}, got {fingerprint}"

    session_file = data.get("activeSessionStateFile")
    if not isinstance(session_file, str) or not session_file.strip():
        return False, "Missing or invalid 'activeSessionStateFile' in pointer"
    session_file_path = Path(session_file)
    if not session_file_path.is_absolute():
        return False, "Pointer field 'activeSessionStateFile' must be absolute"

    session_rel = data.get("activeSessionStateRelativePath")
    if not isinstance(session_rel, str) or not session_rel.strip():
        return False, "Missing or invalid 'activeSessionStateRelativePath' in pointer"
    expected_rel = f"workspaces/{expected_fingerprint}/SESSION_STATE.json"
    normalized_rel = session_rel.replace("\\", "/")
    if normalized_rel != expected_rel:
        return False, f"Relative path mismatch: expected {expected_rel}, got {session_rel}"
    if not str(session_file_path).replace("\\", "/").endswith(expected_rel):
        return False, "Pointer absolute/relative session path mismatch"

    return True, None


def verify_artifacts(workspace_root: Path) -> Tuple[bool, Dict[str, bool], Optional[str]]:
    artifact_names = [
        "repo-cache.yaml",
        "repo-map-digest.md",
        "workspace-memory.yaml",
        "decision-pack.md",
    ]

    results: Dict[str, bool] = {}
    for name in artifact_names:
        results[name] = (workspace_root / name).is_file()

    if all(results.values()):
        return True, results, None
    missing = [k for k, v in results.items() if not v]
    return False, results, f"Missing artifacts: {', '.join(missing)}"


def verify_run_archive(run_root: Path) -> Tuple[bool, Dict[str, bool], Optional[str]]:
    required = [
        "SESSION_STATE.json",
        "metadata.json",
        "run-manifest.json",
        "provenance-record.json",
        "checksums.json",
    ]
    results: Dict[str, bool] = {name: (run_root / name).is_file() for name in required}
    if not all(results.values()):
        missing = [name for name, present in results.items() if not present]
        return False, results, f"Missing run artifacts: {', '.join(missing)}"

    checksums_payload = json.loads((run_root / "checksums.json").read_text(encoding="utf-8"))
    if not isinstance(checksums_payload, dict):
        return False, results, "Invalid checksums.json payload"
    checksum_schema = str(checksums_payload.get("schema") or "").strip()
    if checksum_schema != "governance.run-checksums.v1":
        return False, results, f"Invalid checksums schema: {checksum_schema}"

    files = checksums_payload.get("files")
    if not isinstance(files, dict):
        return False, results, "checksums.json missing files map"

    for rel_name, expected_digest in files.items():
        if not isinstance(rel_name, str) or not isinstance(expected_digest, str):
            return False, results, "checksums.json contains invalid entry"
        candidate = run_root / rel_name
        if not candidate.is_file():
            return False, results, f"Checksum target missing: {rel_name}"
        actual = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected_digest:
            return False, results, f"Checksum mismatch: {rel_name}"

    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return False, results, "Invalid run-manifest.json payload"

    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        return False, results, "Invalid metadata.json payload"

    provenance = json.loads((run_root / "provenance-record.json").read_text(encoding="utf-8"))
    if not isinstance(provenance, dict):
        return False, results, "Invalid provenance-record.json payload"

    run_status = str(manifest.get("run_status") or "").strip()
    record_status = str(manifest.get("record_status") or "").strip()
    run_type = str(manifest.get("run_type") or "").strip()
    integrity_status = str(manifest.get("integrity_status") or "").strip()
    finalized_at = manifest.get("finalized_at")
    required_artifacts = manifest.get("required_artifacts")

    allowed_run_status = {"in_progress", "materialized", "finalized", "failed", "invalidated"}
    allowed_record_status = {"draft", "finalized", "superseded", "invalidated"}
    allowed_run_types = {"analysis", "plan", "pr"}
    if run_status not in allowed_run_status:
        return False, results, f"Invalid run_status: {run_status}"
    if record_status not in allowed_record_status:
        return False, results, f"Invalid record_status: {record_status}"
    if run_type not in allowed_run_types:
        return False, results, f"Invalid run_type: {run_type}"

    if run_status == "finalized":
        if integrity_status != "passed":
            return False, results, "Finalized run must have integrity_status=passed"
        if not isinstance(finalized_at, str) or not finalized_at.strip():
            return False, results, "Finalized run must have finalized_at"

    if not isinstance(required_artifacts, dict):
        return False, results, "run-manifest.json missing required_artifacts map"

    run_id = run_root.name
    manifest_run_id = str(manifest.get("run_id") or "").strip()
    metadata_run_id = str(metadata.get("run_id") or "").strip()
    provenance_run_id = str(provenance.get("run_id") or "").strip()
    if manifest_run_id != run_id:
        return False, results, f"run_id mismatch in run-manifest.json: expected {run_id}, got {manifest_run_id}"
    if metadata_run_id != run_id:
        return False, results, f"run_id mismatch in metadata.json: expected {run_id}, got {metadata_run_id}"
    if provenance_run_id != run_id:
        return False, results, f"run_id mismatch in provenance-record.json: expected {run_id}, got {provenance_run_id}"

    manifest_repo = str(manifest.get("repo_fingerprint") or "").strip()
    metadata_repo = str(metadata.get("repo_fingerprint") or "").strip()
    provenance_repo = str(provenance.get("repo_fingerprint") or "").strip()
    if not manifest_repo or manifest_repo != metadata_repo or metadata_repo != provenance_repo:
        return False, results, "repo_fingerprint mismatch across run-manifest/metadata/provenance"

    provenance_trigger = str(provenance.get("trigger") or "").strip()
    provenance_launcher = str(provenance.get("launcher") or "").strip()
    if provenance_trigger != "new_work_session_created":
        return False, results, f"Invalid provenance trigger: {provenance_trigger}"
    if provenance_launcher != "governance.entrypoints.new_work_session":
        return False, results, f"Invalid provenance launcher: {provenance_launcher}"

    timestamps = provenance.get("timestamps")
    if not isinstance(timestamps, dict):
        return False, results, "provenance-record.json missing timestamps map"
    materialized_at = timestamps.get("materialized_at")
    if not isinstance(materialized_at, str) or not materialized_at.strip():
        return False, results, "provenance-record.json missing timestamps.materialized_at"

    archive_status = str(metadata.get("archive_status") or "").strip()
    finalization_reason = metadata.get("finalization_reason")
    if run_status == "finalized" and archive_status and archive_status != "finalized":
        return False, results, f"archive_status mismatch for finalized run: {archive_status}"
    if run_status == "failed" and archive_status and archive_status != "failed":
        return False, results, f"archive_status mismatch for failed run: {archive_status}"
    if run_status == "finalized":
        if not isinstance(finalization_reason, str) or not finalization_reason.strip():
            return False, results, "Finalized metadata must include finalization_reason"

    for artifact_name, required_flag in required_artifacts.items():
        if not isinstance(artifact_name, str) or not isinstance(required_flag, bool):
            return False, results, "required_artifacts has invalid entries"
        if not required_flag:
            continue
        filename = artifact_name.replace("_", "-") + ".json"
        if artifact_name == "session_state":
            filename = "SESSION_STATE.json"
        if artifact_name == "metadata":
            filename = "metadata.json"
        if artifact_name == "checksums":
            filename = "checksums.json"
        if artifact_name == "run_manifest":
            filename = "run-manifest.json"
        if artifact_name == "provenance":
            filename = "provenance-record.json"
        if not (run_root / filename).is_file():
            return False, results, f"Required artifact missing: {filename}"
        if filename == "checksums.json":
            continue
        if filename not in files:
            return False, results, f"Required artifact not checksummed: {filename}"

    return True, results, None
