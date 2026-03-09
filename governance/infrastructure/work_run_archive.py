from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from governance.domain.canonical_json import canonical_json_hash
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.workspace_paths import (
    plan_record_path,
    run_dir,
    run_metadata_path,
    run_plan_record_path,
    run_session_state_path,
)


@dataclass(frozen=True)
class WorkRunArchiveResult:
    run_id: str
    snapshot_path: Path
    snapshot_digest: str
    metadata_path: Path
    archived_plan_record: bool


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

    archived_state_path = run_session_state_path(workspaces_home, repo_fingerprint, archived_run_id)
    writer(archived_state_path, session_state_document)
    state_digest = canonical_json_hash(session_state_document)

    archived_plan = False
    active_plan_path = plan_record_path(workspaces_home, repo_fingerprint)
    if active_plan_path.exists() and active_plan_path.is_file():
        shutil.copy2(active_plan_path, run_plan_record_path(workspaces_home, repo_fingerprint, archived_run_id))
        archived_plan = True

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
        },
    }
    metadata_path = run_metadata_path(workspaces_home, repo_fingerprint, archived_run_id)
    writer(metadata_path, metadata)

    return WorkRunArchiveResult(
        run_id=archived_run_id,
        snapshot_path=archived_state_path,
        snapshot_digest=state_digest,
        metadata_path=metadata_path,
        archived_plan_record=archived_plan,
    )
