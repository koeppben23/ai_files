from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

RUN_STATUSES = {"in_progress", "materialized", "finalized", "failed", "invalidated"}
RECORD_STATUSES = {"draft", "finalized", "superseded", "invalidated"}
RUNTIME_PURGE_SAFE_FILES = {
    "SESSION_STATE.json",
    "plan-record.json",
    "repo-cache.yaml",
    "repo-map-digest.md",
    "workspace-memory.yaml",
    "decision-pack.md",
    "current_run.json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = []
    prev_dash = False
    for ch in lowered:
        is_word = ("a" <= ch <= "z") or ("0" <= ch <= "9")
        if is_word:
            cleaned.append(ch)
            prev_dash = False
            continue
        if not prev_dash:
            cleaned.append("-")
            prev_dash = True
    result = "".join(cleaned).strip("-")
    return result or "unknown-repository"


def resolve_repo_slug(state_view: Mapping[str, object], repo_fingerprint: str) -> str:
    candidate_keys = (
        "repo_slug",
        "RepoSlug",
        "repository_slug",
        "RepositorySlug",
        "repo_name",
        "RepoName",
    )
    for key in candidate_keys:
        value = state_view.get(key)
        if isinstance(value, str) and value.strip():
            return _slugify(value)
    return repo_fingerprint


def _stable_json_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _artifact_header(
    *,
    schema: str,
    artifact_type: str,
    artifact_id: str,
    run_id: str,
    session_id: str,
    repo_slug: str,
    repo_fingerprint: str,
    created_at: str,
    created_by_component: str,
    classification: str,
    integrity_status: str,
    record_status: str,
    payload: Mapping[str, Any],
    finalized_at: str | None = None,
    finalized_by: str | None = None,
) -> dict[str, object]:
    body = {
        "schema": schema,
        "schema_version": "v1",
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "run_id": run_id,
        "session_id": session_id,
        "repo_slug": repo_slug,
        "repo_fingerprint": repo_fingerprint,
        "created_at": created_at,
        "created_by_component": created_by_component,
        "classification": classification,
        "integrity_status": integrity_status,
        "record_status": record_status,
        "finalized_at": finalized_at,
        "finalized_by": finalized_by,
    }
    body.update(payload)
    body["content_hash"] = _stable_json_hash(payload)
    return body


def build_repository_manifest(
    *,
    repo_fingerprint: str,
    repo_slug: str,
    observed_at: str,
    canonical_remote_url_digest: str,
    default_branch: str,
    tenant_context: str,
    repository_classification: str,
) -> dict[str, object]:
    return {
        "schema": "governance.repository-manifest.v1",
        "schema_version": "v1",
        "artifact_type": "repository_manifest",
        "artifact_id": f"repository-manifest::{repo_fingerprint}",
        "repo_fingerprint": repo_fingerprint,
        "repo_slug": repo_slug,
        "created_at": observed_at,
        "canonical_remote_url_digest": canonical_remote_url_digest,
        "default_branch": default_branch,
        "tenant_context": tenant_context,
        "repository_classification": repository_classification,
        "storage_topology": {
            "runtime_root": "workspaces/<fingerprint>",
            "audit_runs_root": "governance-records/<fingerprint>/runs/<repo_slug>/YYYY/YYYY-MM/YYYY-MM-DD/<run_id>",
        },
    }


def build_run_manifest(
    *,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    source_phase: str,
    source_gate: str,
    source_next: str,
    run_type: str,
    repo_slug: str,
    session_id: str,
    requires_plan_record: bool,
    requires_pr_record: bool,
) -> dict[str, object]:
    return {
        "schema": "governance.run-manifest.v1",
        "schema_version": "v1",
        "artifact_type": "run_manifest",
        "artifact_id": f"run-manifest::{run_id}",
        "repo_fingerprint": repo_fingerprint,
        "repo_slug": repo_slug,
        "run_id": run_id,
        "session_id": session_id,
        "created_at": observed_at,
        "created_by_component": "governance.infrastructure.work_run_archive",
        "classification": "internal",
        "content_hash": "",
        "run_type": run_type,
        "materialized_at": observed_at,
        "source_phase": source_phase,
        "source_active_gate": source_gate,
        "source_next": source_next,
        "run_status": "materialized",
        "record_status": "draft",
        "finalized_at": None,
        "finalized_by": None,
        "integrity_status": "pending",
        "required_artifacts": {
            "session_state": True,
            "run_manifest": True,
            "metadata": True,
            "ticket_record": True,
            "review_decision_record": True,
            "outcome_record": True,
            "evidence_index": True,
            "provenance": True,
            "plan_record": requires_plan_record,
            "pr_record": requires_pr_record,
            "checksums": True,
        },
    }


def classify_run_type(state_view: Mapping[str, object]) -> str:
    pr_title = str(state_view.get("PullRequestTitle") or state_view.get("pr_title") or "").strip()
    pr_body = str(state_view.get("PullRequestBody") or state_view.get("pr_body") or "").strip()
    if pr_title or pr_body:
        return "pr"

    plan_digest = str(state_view.get("PlanRecordDigest") or state_view.get("plan_record_digest") or "").strip()
    plan_status = str(state_view.get("plan_record_status") or state_view.get("PlanRecordStatus") or "").strip().lower()
    plan_versions = state_view.get("plan_record_versions")
    if plan_digest or plan_status in {"active", "finalized", "archived"}:
        return "plan"
    if isinstance(plan_versions, int) and plan_versions > 0:
        return "plan"
    return "analysis"


def finalize_run_manifest(
    manifest: Mapping[str, object],
    *,
    observed_at: str,
    has_plan_record: bool,
    has_pr_record: bool,
    integrity_status: str,
    integrity_error: str = "",
) -> dict[str, object]:
    out = dict(manifest)
    required = manifest.get("required_artifacts")
    required_map = dict(required) if isinstance(required, Mapping) else {}

    missing: list[str] = []
    if bool(required_map.get("plan_record")) and not has_plan_record:
        missing.append("plan_record")
    if bool(required_map.get("pr_record")) and not has_pr_record:
        missing.append("pr_record")

    if integrity_status != "passed":
        out["run_status"] = "failed"
        out["record_status"] = "invalidated"
        out["integrity_status"] = "failed"
        out["finalized_at"] = None
        if missing:
            out["finalization_errors"] = [f"missing-required-artifact:{item}" for item in missing]
        elif integrity_error.strip():
            out["finalization_errors"] = [f"integrity-guard:{integrity_error.strip()}"]
        return out

    if missing:
        out["run_status"] = "failed"
        out["record_status"] = "invalidated"
        out["integrity_status"] = "failed"
        out["finalized_at"] = None
        out["finalization_errors"] = [f"missing-required-artifact:{item}" for item in missing]
        return out

    out["run_status"] = "finalized"
    out["record_status"] = "finalized"
    out["integrity_status"] = "passed"
    out["finalized_at"] = observed_at
    out["finalized_by"] = "governance.finalizer"
    out["content_hash"] = _stable_json_hash(out)
    out.pop("finalization_errors", None)
    return out


def build_provenance_record(
    *,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    state_view: Mapping[str, object],
    repo_slug: str,
    workspace_path_digest: str,
    repository_state_digest: str,
) -> dict[str, object]:
    session_id = str(state_view.get("session_run_id") or run_id)
    model_context_raw = state_view.get("model_context")
    model_context = model_context_raw if isinstance(model_context_raw, dict) else {}
    approval_context_raw = state_view.get("approval_context")
    approval_context = approval_context_raw if isinstance(approval_context_raw, dict) else {}
    payload = {
        "trigger": "new_work_session_created",
        "trigger_type": "new_work_session_created",
        "trigger_source": str(state_view.get("trigger_source") or "governance.runtime"),
        "actor_type": str(state_view.get("actor_type") or "operator"),
        "execution_mode": str(state_view.get("execution_mode") or "standard"),
        "governance_version": str(state_view.get("governance_version") or "v1"),
        "phase_api_hash": str(state_view.get("phase_api_hash") or ""),
        "policy_hashes": [str(state_view.get("spec_hash") or state_view.get("SpecHash") or "")],
        "python_binding": str(state_view.get("python_binding") or ""),
        "launcher_version": str(state_view.get("launcher_version") or "v1"),
        "workspace_path_digest": workspace_path_digest,
        "repository_state_digest": repository_state_digest,
        "started_at": str(state_view.get("started_at") or observed_at),
        "ended_at": observed_at,
        "result": str(state_view.get("result") or "success"),
        "model_context": model_context,
        "approval_context": approval_context,
        "ci_job_ref": str(state_view.get("ci_job_ref") or ""),
        "correlation_id": str(state_view.get("correlation_id") or run_id),
        "policy_fingerprint": str(state_view.get("spec_hash") or state_view.get("SpecHash") or ""),
        "binding": {
            "repo_fingerprint": repo_fingerprint,
            "session_run_id": str(state_view.get("session_run_id") or run_id),
        },
        "launcher": "governance.entrypoints.new_work_session",
        "timestamps": {
            "materialized_at": observed_at,
        },
    }
    return _artifact_header(
        schema="governance.provenance-record.v1",
        artifact_type="provenance_record",
        artifact_id=f"provenance::{run_id}",
        run_id=run_id,
        session_id=session_id,
        repo_slug=repo_slug,
        repo_fingerprint=repo_fingerprint,
        created_at=observed_at,
        created_by_component="governance.infrastructure.work_run_archive",
        classification="internal",
        integrity_status="pending",
        record_status="finalized",
        finalized_at=observed_at,
        finalized_by="governance.materializer",
        payload=payload,
    )


def build_pr_record(
    *,
    state_view: Mapping[str, object],
    repo_fingerprint: str,
    repo_slug: str,
    run_id: str,
    observed_at: str,
) -> dict[str, object] | None:
    title = str(state_view.get("PullRequestTitle") or state_view.get("pr_title") or "").strip()
    body = str(state_view.get("PullRequestBody") or state_view.get("pr_body") or "").strip()
    if not title and not body:
        return None
    session_id = str(state_view.get("session_run_id") or run_id)
    payload = {
        "title": title,
        "body": body,
        "pr_title": title,
        "pr_body": body,
        "pr_body_hash": _stable_json_hash({"pr_body": body}),
        "draft_or_final": "draft" if bool(state_view.get("pr_draft")) else "final",
        "base_branch": str(state_view.get("base_branch") or state_view.get("BaseBranch") or "main"),
        "head_branch": str(state_view.get("head_branch") or state_view.get("HeadBranch") or ""),
        "commit_refs": state_view.get("commit_refs") if isinstance(state_view.get("commit_refs"), list) else [],
        "diff_digest": str(state_view.get("diff_digest") or ""),
        "related_plan_digest": str(state_view.get("PlanRecordDigest") or state_view.get("plan_record_digest") or ""),
        "related_review_decision": str(state_view.get("review_decision") or ""),
        "evidence_refs": state_view.get("evidence_refs") if isinstance(state_view.get("evidence_refs"), list) else [],
        "pr_number": str(state_view.get("pr_number") or ""),
        "pr_url": str(state_view.get("pr_url") or ""),
        "change_scope_summary": str(state_view.get("change_scope_summary") or ""),
        "risk_classification": str(state_view.get("risk_classification") or "unknown"),
        "requires_human_approval": bool(state_view.get("requires_human_approval", False)),
        "approval_status": str(state_view.get("approval_status") or "not-required"),
    }
    return _artifact_header(
        schema="governance.pr-record.v1",
        artifact_type="pr_record",
        artifact_id=f"pr-record::{run_id}",
        run_id=run_id,
        session_id=session_id,
        repo_slug=repo_slug,
        repo_fingerprint=repo_fingerprint,
        created_at=observed_at,
        created_by_component="governance.infrastructure.work_run_archive",
        classification="confidential",
        integrity_status="pending",
        record_status="finalized",
        finalized_at=observed_at,
        finalized_by="governance.materializer",
        payload=payload,
    )


def build_ticket_record(
    *,
    state_view: Mapping[str, object],
    repo_fingerprint: str,
    repo_slug: str,
    run_id: str,
    observed_at: str,
) -> dict[str, object]:
    session_id = str(state_view.get("session_run_id") or run_id)
    payload = {
        "ticket_ref": str(state_view.get("ticket_ref") or state_view.get("TicketRef") or ""),
        "ticket_title": str(state_view.get("ticket_title") or state_view.get("TicketTitle") or ""),
        "ticket_digest": str(state_view.get("TicketRecordDigest") or state_view.get("ticket_digest") or ""),
    }
    return _artifact_header(
        schema="governance.ticket-record.v1",
        artifact_type="ticket_record",
        artifact_id=f"ticket-record::{run_id}",
        run_id=run_id,
        session_id=session_id,
        repo_slug=repo_slug,
        repo_fingerprint=repo_fingerprint,
        created_at=observed_at,
        created_by_component="governance.infrastructure.work_run_archive",
        classification="internal",
        integrity_status="pending",
        record_status="finalized",
        finalized_at=observed_at,
        finalized_by="governance.materializer",
        payload=payload,
    )


def build_review_decision_record(
    *,
    state_view: Mapping[str, object],
    repo_fingerprint: str,
    repo_slug: str,
    run_id: str,
    observed_at: str,
) -> dict[str, object]:
    session_id = str(state_view.get("session_run_id") or run_id)
    payload = {
        "decision": str(state_view.get("review_decision") or "not-applicable"),
        "decision_note": str(state_view.get("review_decision_note") or ""),
    }
    return _artifact_header(
        schema="governance.review-decision-record.v1",
        artifact_type="review_decision_record",
        artifact_id=f"review-decision::{run_id}",
        run_id=run_id,
        session_id=session_id,
        repo_slug=repo_slug,
        repo_fingerprint=repo_fingerprint,
        created_at=observed_at,
        created_by_component="governance.infrastructure.work_run_archive",
        classification="internal",
        integrity_status="pending",
        record_status="finalized",
        finalized_at=observed_at,
        finalized_by="governance.materializer",
        payload=payload,
    )


def build_outcome_record(
    *,
    state_view: Mapping[str, object],
    repo_fingerprint: str,
    repo_slug: str,
    run_id: str,
    observed_at: str,
) -> dict[str, object]:
    session_id = str(state_view.get("session_run_id") or run_id)
    payload = {
        "result": str(state_view.get("result") or "success"),
        "phase": str(state_view.get("Phase") or state_view.get("phase") or ""),
        "active_gate": str(state_view.get("active_gate") or ""),
        "next": str(state_view.get("Next") or state_view.get("next") or ""),
    }
    return _artifact_header(
        schema="governance.outcome-record.v1",
        artifact_type="outcome_record",
        artifact_id=f"outcome-record::{run_id}",
        run_id=run_id,
        session_id=session_id,
        repo_slug=repo_slug,
        repo_fingerprint=repo_fingerprint,
        created_at=observed_at,
        created_by_component="governance.infrastructure.work_run_archive",
        classification="internal",
        integrity_status="pending",
        record_status="finalized",
        finalized_at=observed_at,
        finalized_by="governance.materializer",
        payload=payload,
    )


def build_evidence_index(
    *,
    state_view: Mapping[str, object],
    repo_fingerprint: str,
    repo_slug: str,
    run_id: str,
    observed_at: str,
    archived_files: Mapping[str, bool],
) -> dict[str, object]:
    session_id = str(state_view.get("session_run_id") or run_id)
    payload = {
        "evidence_refs": state_view.get("evidence_refs") if isinstance(state_view.get("evidence_refs"), list) else [],
        "archived_files": dict(archived_files),
    }
    return _artifact_header(
        schema="governance.evidence-index.v1",
        artifact_type="evidence_index",
        artifact_id=f"evidence-index::{run_id}",
        run_id=run_id,
        session_id=session_id,
        repo_slug=repo_slug,
        repo_fingerprint=repo_fingerprint,
        created_at=observed_at,
        created_by_component="governance.infrastructure.work_run_archive",
        classification="internal",
        integrity_status="pending",
        record_status="finalized",
        finalized_at=observed_at,
        finalized_by="governance.materializer",
        payload=payload,
    )


def build_checksums(files: Mapping[str, Path]) -> dict[str, object]:
    digests: dict[str, str] = {}
    for name, path in files.items():
        payload = path.read_bytes()
        digests[name] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return {
        "schema": "governance.run-checksums.v1",
        "files": digests,
    }


def purge_runtime_artifacts(workspace_root: Path) -> list[str]:
    removed: list[str] = []
    for candidate in workspace_root.iterdir():
        if candidate.name == "runs":
            continue
        if candidate.name not in RUNTIME_PURGE_SAFE_FILES:
            continue
        if candidate.is_file():
            candidate.unlink(missing_ok=True)
            removed.append(candidate.name)
    return removed
