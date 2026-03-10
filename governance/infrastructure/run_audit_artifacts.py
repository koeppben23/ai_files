from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Mapping

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


def build_repository_manifest(*, repo_fingerprint: str, observed_at: str) -> dict[str, object]:
    return {
        "schema": "governance.repository-manifest.v1",
        "repo_fingerprint": repo_fingerprint,
        "created_at": observed_at,
        "storage_topology": {
            "runtime_root": "workspaces/<fingerprint>",
            "audit_runs_root": "workspaces/<fingerprint>/runs",
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
    requires_plan_record: bool,
    requires_pr_record: bool,
) -> dict[str, object]:
    return {
        "schema": "governance.run-manifest.v1",
        "repo_fingerprint": repo_fingerprint,
        "run_id": run_id,
        "run_type": run_type,
        "materialized_at": observed_at,
        "source_phase": source_phase,
        "source_active_gate": source_gate,
        "source_next": source_next,
        "run_status": "materialized",
        "record_status": "draft",
        "finalized_at": None,
        "integrity_status": "pending",
        "required_artifacts": {
            "session_state": True,
            "run_manifest": True,
            "metadata": True,
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
    out.pop("finalization_errors", None)
    return out


def build_provenance_record(
    *,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    state_view: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": "governance.provenance-record.v1",
        "repo_fingerprint": repo_fingerprint,
        "run_id": run_id,
        "trigger": "new_work_session_created",
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


def build_pr_record(state_view: Mapping[str, object]) -> dict[str, object] | None:
    title = str(state_view.get("PullRequestTitle") or state_view.get("pr_title") or "").strip()
    body = str(state_view.get("PullRequestBody") or state_view.get("pr_body") or "").strip()
    if not title and not body:
        return None
    return {
        "schema": "governance.pr-record.v1",
        "title": title,
        "body": body,
    }


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
