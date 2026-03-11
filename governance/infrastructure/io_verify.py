import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

from governance.domain.canonical_json import canonical_json_hash


_RFC3339_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REPO_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{24}$")
_SHA256_WITH_PREFIX_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _verify_common_artifact_header(
    payload: dict,
    *,
    expected_schema: str,
    expected_artifact_type: str,
    artifact_label: str,
) -> Optional[str]:
    schema = str(payload.get("schema") or "").strip()
    if schema != expected_schema:
        return f"Invalid {artifact_label} schema: {schema}"
    if str(payload.get("schema_version") or "").strip() != "v1":
        return f"Invalid {artifact_label} schema_version"
    if str(payload.get("artifact_type") or "").strip() != expected_artifact_type:
        return f"Invalid {artifact_label} artifact_type"
    if not str(payload.get("artifact_id") or "").strip():
        return f"{artifact_label} missing artifact_id"
    if not str(payload.get("session_id") or "").strip():
        return f"{artifact_label} missing session_id"
    if not str(payload.get("repo_slug") or "").strip():
        return f"{artifact_label} missing repo_slug"
    if not str(payload.get("created_by_component") or "").strip():
        return f"{artifact_label} missing created_by_component"
    if not str(payload.get("classification") or "").strip():
        return f"{artifact_label} missing classification"
    if str(payload.get("integrity_status") or "").strip() not in {"pending", "passed", "failed"}:
        return f"Invalid {artifact_label} integrity_status"
    if str(payload.get("record_status") or "").strip() not in {"draft", "finalized", "superseded", "invalidated"}:
        return f"Invalid {artifact_label} record_status"
    content_hash = str(payload.get("content_hash") or "").strip()
    if not _SHA256_WITH_PREFIX_RE.match(content_hash):
        return f"Invalid {artifact_label} content_hash"
    return None


def _stable_json_digest(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
        "ticket-record.json",
        "review-decision-record.json",
        "outcome-record.json",
        "evidence-index.json",
        "checksums.json",
    ]
    results: Dict[str, bool] = {name: (run_root / name).is_file() for name in required}
    if not all(results.values()):
        missing = [name for name, present in results.items() if not present]
        return False, results, f"Missing run artifacts: {', '.join(missing)}"

    try:
        checksums_payload = json.loads((run_root / "checksums.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return False, results, f"Failed to parse checksums.json: {exc}"
    if not isinstance(checksums_payload, dict):
        return False, results, "Invalid checksums.json payload"
    checksum_schema = str(checksums_payload.get("schema") or "").strip()
    if checksum_schema != "governance.run-checksums.v1":
        return False, results, f"Invalid checksums schema: {checksum_schema}"

    files = checksums_payload.get("files")
    if not isinstance(files, dict):
        return False, results, "checksums.json missing files map"

    allowed_checksum_targets = {
        "SESSION_STATE.json",
        "metadata.json",
        "run-manifest.json",
        "provenance-record.json",
        "ticket-record.json",
        "review-decision-record.json",
        "outcome-record.json",
        "evidence-index.json",
        "finalization-record.json",
        "plan-record.json",
        "pr-record.json",
    }
    for rel_name in files.keys():
        if rel_name not in allowed_checksum_targets:
            return False, results, f"checksums.json contains unsupported file entry: {rel_name}"

    for rel_name, expected_digest in files.items():
        if not isinstance(rel_name, str) or not isinstance(expected_digest, str):
            return False, results, "checksums.json contains invalid entry"
        candidate = run_root / rel_name
        if not candidate.is_file():
            return False, results, f"Checksum target missing: {rel_name}"
        actual = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected_digest:
            return False, results, f"Checksum mismatch: {rel_name}"

    try:
        manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return False, results, f"Failed to parse run-manifest.json: {exc}"
    if not isinstance(manifest, dict):
        return False, results, "Invalid run-manifest.json payload"
    manifest_schema = str(manifest.get("schema") or "").strip()
    if manifest_schema != "governance.run-manifest.v1":
        return False, results, f"Invalid run-manifest schema: {manifest_schema}"

    try:
        metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return False, results, f"Failed to parse metadata.json: {exc}"
    if not isinstance(metadata, dict):
        return False, results, "Invalid metadata.json payload"
    metadata_schema = str(metadata.get("schema") or "").strip()
    if metadata_schema != "governance.work-run.snapshot.v2":
        return False, results, f"Invalid metadata schema: {metadata_schema}"

    try:
        session_state_document = json.loads((run_root / "SESSION_STATE.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return False, results, f"Failed to parse SESSION_STATE.json: {exc}"
    if not isinstance(session_state_document, dict):
        return False, results, "Invalid SESSION_STATE.json payload"

    snapshot_scope = str(metadata.get("snapshot_digest_scope") or "").strip()
    snapshot_digest = str(metadata.get("snapshot_digest") or "").strip()
    if snapshot_scope != "session_state":
        return False, results, f"Invalid snapshot_digest_scope: {snapshot_scope}"
    if not snapshot_digest:
        return False, results, "metadata.json missing snapshot_digest"
    computed_snapshot_digest = canonical_json_hash(session_state_document)
    if snapshot_digest != computed_snapshot_digest:
        return False, results, "snapshot_digest mismatch for SESSION_STATE.json"

    try:
        provenance = json.loads((run_root / "provenance-record.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return False, results, f"Failed to parse provenance-record.json: {exc}"
    if not isinstance(provenance, dict):
        return False, results, "Invalid provenance-record.json payload"
    provenance_header_error = _verify_common_artifact_header(
        provenance,
        expected_schema="governance.provenance-record.v1",
        expected_artifact_type="provenance_record",
        artifact_label="provenance-record.json",
    )
    if provenance_header_error:
        return False, results, provenance_header_error

    for filename, expected_schema, expected_artifact_type in [
        ("ticket-record.json", "governance.ticket-record.v1", "ticket_record"),
        ("review-decision-record.json", "governance.review-decision-record.v1", "review_decision_record"),
        ("outcome-record.json", "governance.outcome-record.v1", "outcome_record"),
        ("evidence-index.json", "governance.evidence-index.v1", "evidence_index"),
    ]:
        try:
            artifact_payload = json.loads((run_root / filename).read_text(encoding="utf-8"))
        except Exception as exc:
            return False, results, f"Failed to parse {filename}: {exc}"
        if not isinstance(artifact_payload, dict):
            return False, results, f"Invalid {filename} payload"
        artifact_error = _verify_common_artifact_header(
            artifact_payload,
            expected_schema=expected_schema,
            expected_artifact_type=expected_artifact_type,
            artifact_label=filename,
        )
        if artifact_error:
            return False, results, artifact_error

    optional_pr_record = run_root / "pr-record.json"
    if optional_pr_record.is_file():
        try:
            pr_payload = json.loads(optional_pr_record.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, results, f"Failed to parse pr-record.json: {exc}"
        if not isinstance(pr_payload, dict):
            return False, results, "Invalid pr-record.json payload"
        pr_error = _verify_common_artifact_header(
            pr_payload,
            expected_schema="governance.pr-record.v1",
            expected_artifact_type="pr_record",
            artifact_label="pr-record.json",
        )
        if pr_error:
            return False, results, pr_error

    optional_finalization_record = run_root / "finalization-record.json"
    finalization_payload: Optional[dict] = None
    if optional_finalization_record.is_file():
        try:
            parsed_finalization_payload = json.loads(optional_finalization_record.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, results, f"Failed to parse finalization-record.json: {exc}"
        if not isinstance(parsed_finalization_payload, dict):
            return False, results, "Invalid finalization-record.json payload"
        finalization_payload = parsed_finalization_payload
        finalization_error = _verify_common_artifact_header(
            finalization_payload,
            expected_schema="governance.finalization-record.v1",
            expected_artifact_type="finalization_record",
            artifact_label="finalization-record.json",
        )
        if finalization_error:
            return False, results, finalization_error

    run_status = str(manifest.get("run_status") or "").strip()
    record_status = str(manifest.get("record_status") or "").strip()
    run_type = str(manifest.get("run_type") or "").strip()
    integrity_status = str(manifest.get("integrity_status") or "").strip()
    finalized_at = manifest.get("finalized_at")
    finalization_errors = manifest.get("finalization_errors")
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
        if not _RFC3339_UTC_Z_RE.match(finalized_at.strip()):
            return False, results, f"Invalid finalized_at format: {finalized_at}"
        if finalization_errors is not None:
            return False, results, "Finalized run must not include finalization_errors"
        if finalization_payload is None:
            return False, results, "Finalized run must include finalization-record.json"
    elif run_status == "failed":
        if integrity_status != "failed":
            return False, results, "Failed run must have integrity_status=failed"
        if isinstance(finalized_at, str) and finalized_at.strip():
            return False, results, "Failed run must not have finalized_at"
        if record_status != "invalidated":
            return False, results, "Failed run must have record_status=invalidated"
        if not isinstance(finalization_errors, list) or not finalization_errors:
            return False, results, "Failed run must include non-empty finalization_errors"
        for item in finalization_errors:
            if not isinstance(item, str) or not item.strip():
                return False, results, "finalization_errors must contain non-empty strings"
    elif run_status == "materialized":
        if integrity_status != "pending":
            return False, results, "Materialized run must have integrity_status=pending"
        if isinstance(finalized_at, str) and finalized_at.strip():
            return False, results, "Materialized run must not have finalized_at"

    materialized_at_manifest = str(manifest.get("materialized_at") or "").strip()
    archived_at_metadata = str(metadata.get("archived_at") or "").strip()
    if not materialized_at_manifest:
        return False, results, "run-manifest.json missing materialized_at"
    if not archived_at_metadata:
        return False, results, "metadata.json missing archived_at"
    if not _RFC3339_UTC_Z_RE.match(materialized_at_manifest):
        return False, results, f"Invalid run-manifest materialized_at format: {materialized_at_manifest}"
    if not _RFC3339_UTC_Z_RE.match(archived_at_metadata):
        return False, results, f"Invalid metadata archived_at format: {archived_at_metadata}"
    if materialized_at_manifest != archived_at_metadata:
        return False, results, "materialized_at/archived_at mismatch between run-manifest and metadata"

    if not isinstance(required_artifacts, dict):
        return False, results, "run-manifest.json missing required_artifacts map"

    expected_artifact_keys = {
        "session_state",
        "run_manifest",
        "metadata",
        "ticket_record",
        "review_decision_record",
        "outcome_record",
        "evidence_index",
        "provenance",
        "plan_record",
        "pr_record",
        "checksums",
    }
    required_keys = set(required_artifacts.keys())
    if required_keys != expected_artifact_keys:
        missing = sorted(expected_artifact_keys - required_keys)
        extra = sorted(required_keys - expected_artifact_keys)
        return False, results, f"required_artifacts key mismatch: missing={missing}, extra={extra}"
    baseline_required_true = [
        "session_state",
        "run_manifest",
        "metadata",
        "ticket_record",
        "review_decision_record",
        "outcome_record",
        "evidence_index",
        "provenance",
        "checksums",
    ]
    for key in baseline_required_true:
        if required_artifacts.get(key) is not True:
            return False, results, f"required_artifacts.{key} must be true"

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
    if not _REPO_FINGERPRINT_RE.match(manifest_repo):
        return False, results, f"Invalid repo_fingerprint format: {manifest_repo}"

    provenance_trigger = str(provenance.get("trigger") or "").strip()
    provenance_launcher = str(provenance.get("launcher") or "").strip()
    if provenance_trigger != "new_work_session_created":
        return False, results, f"Invalid provenance trigger: {provenance_trigger}"
    if provenance_launcher != "governance.entrypoints.new_work_session":
        return False, results, f"Invalid provenance launcher: {provenance_launcher}"

    binding = provenance.get("binding")
    if not isinstance(binding, dict):
        return False, results, "provenance-record.json missing binding map"
    binding_repo = str(binding.get("repo_fingerprint") or "").strip()
    binding_session_run_id = str(binding.get("session_run_id") or "").strip()
    if binding_repo != manifest_repo:
        return False, results, "provenance binding repo_fingerprint mismatch"
    if binding_session_run_id != run_id:
        return False, results, "provenance binding session_run_id mismatch"

    timestamps = provenance.get("timestamps")
    if not isinstance(timestamps, dict):
        return False, results, "provenance-record.json missing timestamps map"
    materialized_at = timestamps.get("materialized_at")
    if not isinstance(materialized_at, str) or not materialized_at.strip():
        return False, results, "provenance-record.json missing timestamps.materialized_at"
    if not _RFC3339_UTC_Z_RE.match(materialized_at.strip()):
        return False, results, f"Invalid provenance materialized_at format: {materialized_at}"
    if str(materialized_at).strip() != materialized_at_manifest:
        return False, results, "materialized_at mismatch between run-manifest and provenance"

    archived_files = metadata.get("archived_files")
    if not isinstance(archived_files, dict):
        return False, results, "metadata.json missing archived_files map"
    expected_archived_keys = {
        "session_state",
        "plan_record",
        "pr_record",
        "ticket_record",
        "review_decision_record",
        "outcome_record",
        "evidence_index",
        "run_manifest",
        "provenance_record",
        "checksums",
    }
    archived_keys = set(archived_files.keys())
    if archived_keys != expected_archived_keys:
        missing = sorted(expected_archived_keys - archived_keys)
        extra = sorted(archived_keys - expected_archived_keys)
        return False, results, f"archived_files key mismatch: missing={missing}, extra={extra}"
    for key, value in archived_files.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            return False, results, "archived_files has invalid entries"
    if archived_files.get("session_state") is not True:
        return False, results, "archived_files.session_state must be true"
    baseline_archived_true = [
        "ticket_record",
        "review_decision_record",
        "outcome_record",
        "evidence_index",
        "run_manifest",
        "provenance_record",
        "checksums",
    ]
    for key in baseline_archived_true:
        if archived_files.get(key) is not True:
            return False, results, f"archived_files.{key} must be true"

    archived_file_to_name = {
        "session_state": "SESSION_STATE.json",
        "plan_record": "plan-record.json",
        "pr_record": "pr-record.json",
        "ticket_record": "ticket-record.json",
        "review_decision_record": "review-decision-record.json",
        "outcome_record": "outcome-record.json",
        "evidence_index": "evidence-index.json",
        "run_manifest": "run-manifest.json",
        "provenance_record": "provenance-record.json",
        "checksums": "checksums.json",
    }
    for key, filename in archived_file_to_name.items():
        expected_present = bool(archived_files.get(key))
        actual_present = (run_root / filename).is_file()
        if expected_present != actual_present:
            return False, results, f"archived_files mismatch for {filename}: expected={expected_present}, actual={actual_present}"

    archive_status = str(metadata.get("archive_status") or "").strip()
    finalization_reason = metadata.get("finalization_reason")
    failure_reason = metadata.get("failure_reason")
    allowed_archive_status = {"materialized", "finalized", "failed"}
    if archive_status not in allowed_archive_status:
        return False, results, f"Invalid archive_status: {archive_status}"
    if run_status == "finalized" and archive_status and archive_status != "finalized":
        return False, results, f"archive_status mismatch for finalized run: {archive_status}"
    if run_status == "failed" and archive_status and archive_status != "failed":
        return False, results, f"archive_status mismatch for failed run: {archive_status}"
    if run_status == "finalized":
        if not isinstance(finalization_reason, str) or not finalization_reason.strip():
            return False, results, "Finalized metadata must include finalization_reason"
        if isinstance(failure_reason, str) and failure_reason.strip():
            return False, results, "Finalized metadata must not include failure_reason"
    if run_status == "failed":
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            return False, results, "Failed metadata must include failure_reason"
        if isinstance(finalization_reason, str) and finalization_reason.strip():
            return False, results, "Failed metadata must not include finalization_reason"

    plan_required = bool(required_artifacts.get("plan_record"))
    pr_required = bool(required_artifacts.get("pr_record"))
    plan_archived = bool(archived_files.get("plan_record"))
    pr_archived = bool(archived_files.get("pr_record"))
    if run_type == "plan":
        if not plan_required or pr_required:
            return False, results, "plan run_type requires plan_record=true and pr_record=false"
    elif run_type == "pr":
        if not pr_required or plan_required:
            return False, results, "pr run_type requires pr_record=true and plan_record=false"
    elif run_type == "analysis":
        if plan_required or pr_required:
            return False, results, "analysis run_type requires plan_record=false and pr_record=false"
    if plan_required and not plan_archived:
        return False, results, "required plan_record must be archived"
    if pr_required and not pr_archived:
        return False, results, "required pr_record must be archived"

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

    present_optional = [
        "plan-record.json",
        "pr-record.json",
        "finalization-record.json",
    ]
    for filename in present_optional:
        if (run_root / filename).is_file() and filename not in files:
            return False, results, f"Present artifact not checksummed: {filename}"

    if run_status == "finalized" and finalization_payload is not None:
        finalization_run_status = str(finalization_payload.get("run_status") or "").strip()
        if finalization_run_status != run_status:
            return False, results, "finalization-record run_status mismatch"
        finalization_manifest_status = str(finalization_payload.get("manifest_record_status") or "").strip()
        if finalization_manifest_status != record_status:
            return False, results, "finalization-record manifest_record_status mismatch"
        finalization_integrity_status = str(finalization_payload.get("manifest_integrity_status") or "").strip()
        if finalization_integrity_status != integrity_status:
            return False, results, "finalization-record manifest_integrity_status mismatch"
        checksums_without_finalization = {
            key: value
            for key, value in files.items()
            if key != "finalization-record.json"
        }
        expected_bundle_hash = _stable_json_digest(
            {
                "run_id": run_root.name,
                "manifest": manifest,
                "checksums": checksums_without_finalization,
            }
        )
        actual_bundle_hash = str(finalization_payload.get("bundle_manifest_hash") or "").strip()
        if actual_bundle_hash != expected_bundle_hash:
            return False, results, "finalization-record bundle_manifest_hash mismatch"

    return True, results, None


def verify_repository_manifest(runs_root: Path, *, expected_repo_fingerprint: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    manifest_path = runs_root / "repository-manifest.json"
    if not manifest_path.is_file():
        return False, f"Missing repository manifest: {manifest_path.name}"

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"Failed to parse repository-manifest.json: {exc}"

    if not isinstance(payload, dict):
        return False, "Invalid repository-manifest.json payload"

    schema = str(payload.get("schema") or "").strip()
    if schema != "governance.repository-manifest.v1":
        return False, f"Invalid repository manifest schema: {schema}"
    if str(payload.get("schema_version") or "").strip() != "v1":
        return False, "repository-manifest.json missing schema_version=v1"
    if str(payload.get("artifact_type") or "").strip() != "repository_manifest":
        return False, "repository-manifest.json missing artifact_type=repository_manifest"
    if not str(payload.get("artifact_id") or "").strip():
        return False, "repository-manifest.json missing artifact_id"

    repo_slug = str(payload.get("repo_slug") or "").strip()
    if not repo_slug:
        return False, "repository-manifest.json missing repo_slug"

    canonical_remote_url_digest = str(payload.get("canonical_remote_url_digest") or "").strip()
    if not canonical_remote_url_digest:
        return False, "repository-manifest.json missing canonical_remote_url_digest"
    if not re.match(r"^(sha256:)?[0-9a-f]{64}$", canonical_remote_url_digest):
        return False, "repository-manifest.json invalid canonical_remote_url_digest"

    if not str(payload.get("default_branch") or "").strip():
        return False, "repository-manifest.json missing default_branch"
    if not str(payload.get("tenant_context") or "").strip():
        return False, "repository-manifest.json missing tenant_context"
    if not str(payload.get("repository_classification") or "").strip():
        return False, "repository-manifest.json missing repository_classification"

    repo_fingerprint = str(payload.get("repo_fingerprint") or "").strip()
    if not repo_fingerprint:
        return False, "repository-manifest.json missing repo_fingerprint"
    if not _REPO_FINGERPRINT_RE.match(repo_fingerprint):
        return False, f"Invalid repository manifest repo_fingerprint format: {repo_fingerprint}"
    parent_fingerprint = runs_root.parent.name
    if _REPO_FINGERPRINT_RE.match(parent_fingerprint) and repo_fingerprint != parent_fingerprint:
        return (
            False,
            f"repository manifest fingerprint/path mismatch: expected {parent_fingerprint}, got {repo_fingerprint}",
        )
    if expected_repo_fingerprint and repo_fingerprint != expected_repo_fingerprint:
        return (
            False,
            f"repository manifest fingerprint mismatch: expected {expected_repo_fingerprint}, got {repo_fingerprint}",
        )

    created_at = str(payload.get("created_at") or "").strip()
    if not created_at:
        return False, "repository-manifest.json missing created_at"
    if not _RFC3339_UTC_Z_RE.match(created_at):
        return False, f"Invalid repository manifest created_at format: {created_at}"

    topology = payload.get("storage_topology")
    if not isinstance(topology, dict):
        return False, "repository-manifest.json missing storage_topology"

    runtime_root = str(topology.get("runtime_root") or "").strip()
    audit_runs_root = str(topology.get("audit_runs_root") or "").strip()
    if runtime_root != "workspaces/<fingerprint>":
        return False, f"Invalid runtime_root in repository manifest: {runtime_root}"
    if audit_runs_root != "governance-records/<fingerprint>/runs/<repo_slug>/YYYY/YYYY-MM/YYYY-MM-DD/<run_id>":
        return False, f"Invalid audit_runs_root in repository manifest: {audit_runs_root}"

    return True, None
