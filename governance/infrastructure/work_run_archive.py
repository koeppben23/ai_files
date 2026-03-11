from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from governance.domain.canonical_json import canonical_json_hash
from governance.domain.access_control import Action, AccessDecision, Role, evaluate_access
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.run_audit_artifacts import (
    build_checksums,
    classify_run_type,
    build_evidence_index,
    build_finalization_record,
    finalize_run_manifest,
    build_outcome_record,
    build_pr_record,
    build_provenance_record,
    build_review_decision_record,
    build_repository_manifest,
    build_ticket_record,
    build_run_manifest,
    resolve_repo_slug,
)
from governance.infrastructure.workspace_paths import (
    repository_manifest_path,
    run_checksums_path,
    run_evidence_index_path,
    run_finalization_record_path,
    plan_record_path,
    run_dir,
    run_outcome_record_path,
    run_manifest_path,
    run_metadata_path,
    run_plan_record_path,
    run_pr_record_path,
    run_provenance_path,
    run_review_decision_record_path,
    run_session_state_path,
    run_ticket_record_path,
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


def _regulated_mode_active(state_view: Mapping[str, object]) -> bool:
    state = str(state_view.get("regulated_mode_state") or state_view.get("regulated_mode") or "").strip().lower()
    return state in {"active", "transitioning", "true", "1", "yes"}


def _regulated_finalization_guard(
    *,
    state_view: Mapping[str, object],
    run_type: str,
) -> tuple[bool, str]:
    if not _regulated_mode_active(state_view):
        return True, "regulated-mode-inactive"
    requires_human_approval = bool(state_view.get("requires_human_approval", run_type == "pr"))
    approval_status = str(state_view.get("approval_status") or "").strip().lower()
    if requires_human_approval and approval_status != "approved":
        return False, "regulated mode requires approved human approval before finalization"
    if requires_human_approval:
        role_raw = str(state_view.get("role") or state_view.get("actor_role") or "operator").strip().lower()
        approver_raw = str(state_view.get("approver_role") or "").strip().lower()

        try:
            initiator_role = Role(role_raw)
        except ValueError:
            return False, f"regulated mode finalization denied: unknown initiator role '{role_raw}'"

        approver_role: Role | None = None
        if approver_raw:
            try:
                approver_role = Role(approver_raw)
            except ValueError:
                return False, f"regulated mode finalization denied: unknown approver role '{approver_raw}'"

        access = evaluate_access(
            role=initiator_role,
            action=Action.FINALIZE_RUN,
            regulated_mode_active=True,
            approver_role=approver_role,
        )
        if access.decision != AccessDecision.ALLOW:
            return False, (
                "regulated mode finalization denied: "
                f"{access.reason}; approval={access.approval_reason}"
            )
    return True, "regulated-mode-guard-passed"


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
    repo_slug = resolve_repo_slug(state_view, repo_fingerprint)
    archive_root = run_dir(
        workspaces_home,
        repo_fingerprint,
        archived_run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    )

    if archive_root.exists():
        existing_manifest = archive_root / "run-manifest.json"
        if existing_manifest.exists() and existing_manifest.is_file():
            try:
                existing_payload = json.loads(existing_manifest.read_text(encoding="utf-8"))
            except Exception:
                existing_payload = {}
            existing_status = str(existing_payload.get("run_status") or "").strip()
            if existing_status == "failed":
                shutil.rmtree(archive_root, ignore_errors=True)
            else:
                raise RuntimeError(f"run archive already exists: {archive_root}")
        else:
            raise RuntimeError(f"run archive already exists: {archive_root}")
    archive_root.mkdir(parents=True, exist_ok=False)

    try:
        canonical_remote_url_digest = canonical_json_hash({"remote": str(state_view.get("remote_url") or "")})
        repository_manifest = repository_manifest_path(workspaces_home, repo_fingerprint)
        if not repository_manifest.exists():
            repository_manifest.parent.mkdir(parents=True, exist_ok=True)
            writer(
                repository_manifest,
                build_repository_manifest(
                    repo_fingerprint=repo_fingerprint,
                    repo_slug=repo_slug,
                    observed_at=observed_at,
                    canonical_remote_url_digest=canonical_remote_url_digest,
                    default_branch=str(state_view.get("default_branch") or "main"),
                    tenant_context=str(state_view.get("tenant_context") or "default"),
                    repository_classification=str(state_view.get("repository_classification") or "internal"),
                ),
            )

        archived_state_path = run_session_state_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        writer(archived_state_path, session_state_document)
        state_digest = canonical_json_hash(session_state_document)

        archived_plan = False
        active_plan_path = plan_record_path(workspaces_home, repo_fingerprint)
        if active_plan_path.exists() and active_plan_path.is_file():
            shutil.copy2(
                active_plan_path,
                run_plan_record_path(
                    workspaces_home,
                    repo_fingerprint,
                    archived_run_id,
                    repo_slug=repo_slug,
                    observed_at=observed_at,
                ),
            )
            archived_plan = True

        run_type = classify_run_type(state_view)
        pr_record_doc = build_pr_record(
            state_view=state_view,
            repo_fingerprint=repo_fingerprint,
            repo_slug=repo_slug,
            run_id=archived_run_id,
            observed_at=observed_at,
        )
        archived_pr = False
        if pr_record_doc is not None:
            writer(
                run_pr_record_path(
                    workspaces_home,
                    repo_fingerprint,
                    archived_run_id,
                    repo_slug=repo_slug,
                    observed_at=observed_at,
                ),
                pr_record_doc,
            )
            archived_pr = True

        ticket_record = build_ticket_record(
            state_view=state_view,
            repo_fingerprint=repo_fingerprint,
            repo_slug=repo_slug,
            run_id=archived_run_id,
            observed_at=observed_at,
        )
        writer(
            run_ticket_record_path(
                workspaces_home,
                repo_fingerprint,
                archived_run_id,
                repo_slug=repo_slug,
                observed_at=observed_at,
            ),
            ticket_record,
        )

        review_decision_record = build_review_decision_record(
            state_view=state_view,
            repo_fingerprint=repo_fingerprint,
            repo_slug=repo_slug,
            run_id=archived_run_id,
            observed_at=observed_at,
        )
        writer(
            run_review_decision_record_path(
                workspaces_home,
                repo_fingerprint,
                archived_run_id,
                repo_slug=repo_slug,
                observed_at=observed_at,
            ),
            review_decision_record,
        )

        outcome_record = build_outcome_record(
            state_view=state_view,
            repo_fingerprint=repo_fingerprint,
            repo_slug=repo_slug,
            run_id=archived_run_id,
            observed_at=observed_at,
        )
        writer(
            run_outcome_record_path(
                workspaces_home,
                repo_fingerprint,
                archived_run_id,
                repo_slug=repo_slug,
                observed_at=observed_at,
            ),
            outcome_record,
        )

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
                "ticket_record": True,
                "review_decision_record": True,
                "outcome_record": True,
                "evidence_index": True,
                "run_manifest": True,
                "provenance_record": True,
                "checksums": True,
            },
            "archive_status": "materialized",
        }
        metadata_path = run_metadata_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        writer(metadata_path, metadata)

        run_manifest = build_run_manifest(
            repo_fingerprint=repo_fingerprint,
            run_id=archived_run_id,
            observed_at=observed_at,
            source_phase=str(state_view.get("Phase") or state_view.get("phase") or ""),
            source_gate=str(state_view.get("active_gate") or ""),
            source_next=str(state_view.get("Next") or state_view.get("next") or ""),
            run_type=run_type,
            repo_slug=repo_slug,
            session_id=str(state_view.get("session_run_id") or archived_run_id),
            requires_plan_record=(run_type == "plan"),
            requires_pr_record=(run_type == "pr"),
        )
        writer(
            run_manifest_path(
                workspaces_home,
                repo_fingerprint,
                archived_run_id,
                repo_slug=repo_slug,
                observed_at=observed_at,
            ),
            run_manifest,
        )

        workspace_digest = canonical_json_hash({"workspace_path": str(workspaces_home / repo_fingerprint)})
        writer(
            run_provenance_path(
                workspaces_home,
                repo_fingerprint,
                archived_run_id,
                repo_slug=repo_slug,
                observed_at=observed_at,
            ),
            build_provenance_record(
                repo_fingerprint=repo_fingerprint,
                run_id=archived_run_id,
                observed_at=observed_at,
                state_view=state_view,
                repo_slug=repo_slug,
                workspace_path_digest=workspace_digest,
                repository_state_digest=state_digest,
            ),
        )

        evidence_index = build_evidence_index(
            state_view=state_view,
            repo_fingerprint=repo_fingerprint,
            repo_slug=repo_slug,
            run_id=archived_run_id,
            observed_at=observed_at,
            archived_files=metadata["archived_files"],
        )
        writer(
            run_evidence_index_path(
                workspaces_home,
                repo_fingerprint,
                archived_run_id,
                repo_slug=repo_slug,
                observed_at=observed_at,
            ),
            evidence_index,
        )

        checksum_inputs: dict[str, Path] = {
            "SESSION_STATE.json": archived_state_path,
            "metadata.json": metadata_path,
            "run-manifest.json": run_manifest_path(
                workspaces_home, repo_fingerprint, archived_run_id, repo_slug=repo_slug, observed_at=observed_at
            ),
            "provenance-record.json": run_provenance_path(
                workspaces_home, repo_fingerprint, archived_run_id, repo_slug=repo_slug, observed_at=observed_at
            ),
            "ticket-record.json": run_ticket_record_path(
                workspaces_home, repo_fingerprint, archived_run_id, repo_slug=repo_slug, observed_at=observed_at
            ),
            "review-decision-record.json": run_review_decision_record_path(
                workspaces_home, repo_fingerprint, archived_run_id, repo_slug=repo_slug, observed_at=observed_at
            ),
            "outcome-record.json": run_outcome_record_path(
                workspaces_home, repo_fingerprint, archived_run_id, repo_slug=repo_slug, observed_at=observed_at
            ),
            "evidence-index.json": run_evidence_index_path(
                workspaces_home, repo_fingerprint, archived_run_id, repo_slug=repo_slug, observed_at=observed_at
            ),
        }
        plan_path = run_plan_record_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        if plan_path.exists() and plan_path.is_file():
            checksum_inputs["plan-record.json"] = plan_path
        pr_path = run_pr_record_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        if pr_path.exists() and pr_path.is_file():
            checksum_inputs["pr-record.json"] = pr_path

        checksums_path = run_checksums_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        writer(checksums_path, build_checksums(checksum_inputs))

        integrity_ok, _, integrity_message = verify_run_archive(archive_root)
        guard_ok, guard_reason = _regulated_finalization_guard(state_view=state_view, run_type=run_type)
        if not guard_ok:
            integrity_ok = False
            integrity_message = guard_reason
        finalized_manifest = finalize_run_manifest(
            run_manifest,
            observed_at=observed_at,
            has_plan_record=archived_plan,
            has_pr_record=archived_pr,
            integrity_status="passed" if integrity_ok else "failed",
            integrity_error=str(integrity_message or ""),
        )
        manifest_path = run_manifest_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        writer(manifest_path, finalized_manifest)
        if str(finalized_manifest.get("run_status") or "") != "finalized":
            errors = finalized_manifest.get("finalization_errors")
            if isinstance(errors, list) and errors:
                raise RuntimeError(f"run archive failed finalization guards: {errors[0]}")
            raise RuntimeError("run archive failed finalization guards")

        metadata["archive_status"] = "finalized"
        metadata["finalization_reason"] = "all-required-artifacts-present-and-verified"
        writer(metadata_path, metadata)
        checksums_payload = build_checksums(checksum_inputs)
        finalization_record = build_finalization_record(
            repo_fingerprint=repo_fingerprint,
            repo_slug=repo_slug,
            run_id=archived_run_id,
            observed_at=observed_at,
            finalized_manifest=finalized_manifest,
            checksums_payload=checksums_payload,
            finalization_reason="all-required-artifacts-present-and-verified",
        )
        finalization_record_path = run_finalization_record_path(
            workspaces_home,
            repo_fingerprint,
            archived_run_id,
            repo_slug=repo_slug,
            observed_at=observed_at,
        )
        writer(finalization_record_path, finalization_record)
        checksum_inputs["run-manifest.json"] = manifest_path
        checksum_inputs["finalization-record.json"] = finalization_record_path
        writer(checksums_path, build_checksums(checksum_inputs))
        integrity_ok, _, integrity_message = verify_run_archive(archive_root)
        if not integrity_ok:
            raise RuntimeError(
                f"run archive integrity verify failed after metadata finalization: {integrity_message or 'unknown'}"
            )
    except Exception as exc:
        error_message = str(exc)
        try:
            fail_metadata = {
                "schema": "governance.work-run.snapshot.v2",
                "repo_fingerprint": repo_fingerprint,
                "run_id": archived_run_id,
                "archived_at": observed_at,
                "source_phase": str(state_view.get("Phase") or state_view.get("phase") or ""),
                "source_active_gate": str(state_view.get("active_gate") or ""),
                "source_next": str(state_view.get("Next") or state_view.get("next") or ""),
                "snapshot_digest": "",
                "snapshot_digest_scope": "session_state",
                "archived_files": {
                    "session_state": False,
                    "plan_record": False,
                    "pr_record": False,
                    "ticket_record": False,
                    "review_decision_record": False,
                    "outcome_record": False,
                    "evidence_index": False,
                    "run_manifest": False,
                    "provenance_record": False,
                    "checksums": False,
                },
                "archive_status": "failed",
                "failure_reason": error_message,
            }
            _write_json_atomic(
                run_metadata_path(
                    workspaces_home,
                    repo_fingerprint,
                    archived_run_id,
                    repo_slug=repo_slug,
                    observed_at=observed_at,
                ),
                fail_metadata,
            )

            fail_manifest = {
                "schema": "governance.run-manifest.v1",
                "repo_fingerprint": repo_fingerprint,
                "run_id": archived_run_id,
                "run_type": "analysis",
                "materialized_at": observed_at,
                "source_phase": str(state_view.get("Phase") or state_view.get("phase") or ""),
                "source_active_gate": str(state_view.get("active_gate") or ""),
                "source_next": str(state_view.get("Next") or state_view.get("next") or ""),
                "run_status": "failed",
                "record_status": "invalidated",
                "finalized_at": None,
                "integrity_status": "failed",
                "required_artifacts": {
                    "session_state": True,
                    "run_manifest": True,
                    "metadata": True,
                    "ticket_record": True,
                    "review_decision_record": True,
                    "outcome_record": True,
                    "evidence_index": True,
                    "provenance": True,
                    "plan_record": False,
                    "pr_record": False,
                    "checksums": True,
                },
                "finalization_errors": [f"archive-error:{error_message}"],
            }
            _write_json_atomic(
                run_manifest_path(
                    workspaces_home,
                    repo_fingerprint,
                    archived_run_id,
                    repo_slug=repo_slug,
                    observed_at=observed_at,
                ),
                fail_manifest,
            )
        except Exception:
            pass
        raise

    return WorkRunArchiveResult(
        run_id=archived_run_id,
        snapshot_path=archived_state_path,
        snapshot_digest=state_digest,
        metadata_path=metadata_path,
        archived_plan_record=archived_plan,
        archived_pr_record=archived_pr,
    )
