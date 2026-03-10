from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from governance.domain.canonical_json import canonical_json_hash
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.run_audit_artifacts import (
    build_checksums,
    classify_run_type,
    finalize_run_manifest,
    build_pr_record,
    build_provenance_record,
    build_repository_manifest,
    build_run_manifest,
)
from governance.infrastructure.workspace_paths import (
    repository_manifest_path,
    run_checksums_path,
    plan_record_path,
    run_dir,
    run_manifest_path,
    run_metadata_path,
    run_plan_record_path,
    run_pr_record_path,
    run_provenance_path,
    run_session_state_path,
)


@dataclass(frozen=True)
class WorkRunArchiveResult:
    run_id: str
    snapshot_path: Path
    snapshot_digest: str
    metadata_path: Path
    archived_plan_record: bool
    archived_pr_record: bool


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    atomic_write_text(path, text)


def archive_active_run(
    *,
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    session_state_document: Mapping[str, object],
    state_view: Mapping[str, object],
    write_json_atomic: Callable[[Path, Mapping[str, object]], None] | None = None,
) -> WorkRunArchiveResult:
    writer = write_json_atomic or _write_json_atomic
    archived_run_id = run_id
    archive_root = run_dir(workspaces_home, repo_fingerprint, archived_run_id)

    if archive_root.exists():
        raise RuntimeError(f"run archive already exists: {archive_root}")
    archive_root.mkdir(parents=True, exist_ok=False)

    try:
        repository_manifest = repository_manifest_path(workspaces_home, repo_fingerprint)
        if not repository_manifest.exists():
            repository_manifest.parent.mkdir(parents=True, exist_ok=True)
            writer(
                repository_manifest,
                build_repository_manifest(repo_fingerprint=repo_fingerprint, observed_at=observed_at),
            )

        archived_state_path = run_session_state_path(workspaces_home, repo_fingerprint, archived_run_id)
        writer(archived_state_path, session_state_document)
        state_digest = canonical_json_hash(session_state_document)

        archived_plan = False
        active_plan_path = plan_record_path(workspaces_home, repo_fingerprint)
        if active_plan_path.exists() and active_plan_path.is_file():
            shutil.copy2(active_plan_path, run_plan_record_path(workspaces_home, repo_fingerprint, archived_run_id))
            archived_plan = True

        run_type = classify_run_type(state_view)
        pr_record_doc = build_pr_record(state_view)
        archived_pr = False
        if pr_record_doc is not None:
            writer(run_pr_record_path(workspaces_home, repo_fingerprint, archived_run_id), pr_record_doc)
            archived_pr = True

        metadata = {
            "schema": "governance.work-run.snapshot.v2",
            "repo_fingerprint": repo_fingerprint,
            "run_id": archived_run_id,
            "archived_at": observed_at,
            "source_phase": str(state_view.get("Phase") or state_view.get("phase") or ""),
            "source_active_gate": str(state_view.get("active_gate") or ""),
            "source_next": str(state_view.get("Next") or state_view.get("next") or ""),
            "snapshot_digest": state_digest,
            "snapshot_digest_scope": "session_state",
            "ticket_digest": state_view.get("TicketRecordDigest"),
            "task_digest": state_view.get("TaskRecordDigest"),
            "plan_record_digest": state_view.get("PlanRecordDigest") or state_view.get("plan_record_digest"),
            "impl_digest": state_view.get("ImplementationDigest") or state_view.get("implementation_digest"),
            "archived_files": {
                "session_state": True,
                "plan_record": archived_plan,
                "pr_record": archived_pr,
            },
        }
        metadata_path = run_metadata_path(workspaces_home, repo_fingerprint, archived_run_id)
        writer(metadata_path, metadata)

        run_manifest = build_run_manifest(
            repo_fingerprint=repo_fingerprint,
            run_id=archived_run_id,
            observed_at=observed_at,
            source_phase=str(state_view.get("Phase") or state_view.get("phase") or ""),
            source_gate=str(state_view.get("active_gate") or ""),
            source_next=str(state_view.get("Next") or state_view.get("next") or ""),
            run_type=run_type,
            requires_plan_record=(run_type == "plan"),
            requires_pr_record=(run_type == "pr"),
        )
        writer(run_manifest_path(workspaces_home, repo_fingerprint, archived_run_id), run_manifest)

        writer(
            run_provenance_path(workspaces_home, repo_fingerprint, archived_run_id),
            build_provenance_record(
                repo_fingerprint=repo_fingerprint,
                run_id=archived_run_id,
                observed_at=observed_at,
                state_view=state_view,
            ),
        )

        checksum_inputs: dict[str, Path] = {
            "SESSION_STATE.json": archived_state_path,
            "metadata.json": metadata_path,
            "run-manifest.json": run_manifest_path(workspaces_home, repo_fingerprint, archived_run_id),
            "provenance-record.json": run_provenance_path(workspaces_home, repo_fingerprint, archived_run_id),
        }
        plan_path = run_plan_record_path(workspaces_home, repo_fingerprint, archived_run_id)
        if plan_path.exists() and plan_path.is_file():
            checksum_inputs["plan-record.json"] = plan_path
        pr_path = run_pr_record_path(workspaces_home, repo_fingerprint, archived_run_id)
        if pr_path.exists() and pr_path.is_file():
            checksum_inputs["pr-record.json"] = pr_path

        checksums_path = run_checksums_path(workspaces_home, repo_fingerprint, archived_run_id)
        writer(checksums_path, build_checksums(checksum_inputs))

        integrity_ok, _, _ = verify_run_archive(archive_root)
        finalized_manifest = finalize_run_manifest(
            run_manifest,
            observed_at=observed_at,
            has_plan_record=archived_plan,
            has_pr_record=archived_pr,
            integrity_status="passed" if integrity_ok else "failed",
        )
        manifest_path = run_manifest_path(workspaces_home, repo_fingerprint, archived_run_id)
        writer(manifest_path, finalized_manifest)
        checksum_inputs["run-manifest.json"] = manifest_path
        writer(checksums_path, build_checksums(checksum_inputs))
        integrity_ok, _, _ = verify_run_archive(archive_root)
        if not integrity_ok:
            raise RuntimeError("run archive integrity verify failed")
        if str(finalized_manifest.get("run_status") or "") != "finalized":
            raise RuntimeError("run archive failed finalization guards")
    except Exception:
        shutil.rmtree(archive_root, ignore_errors=True)
        raise

    return WorkRunArchiveResult(
        run_id=archived_run_id,
        snapshot_path=archived_state_path,
        snapshot_digest=state_digest,
        metadata_path=metadata_path,
        archived_plan_record=archived_plan,
        archived_pr_record=archived_pr,
    )
