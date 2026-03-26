from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_provenance_record_with_required_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-prov",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
        "SpecHash": "sha256:policy123",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-prov",
        observed_at="2026-03-10T12:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record_path = run_dir(workspaces_home, fingerprint, "run-prov") / "provenance-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["schema"] == "governance.provenance-record.v1"
    assert record["repo_fingerprint"] == fingerprint
    assert record["run_id"] == "run-prov"
    assert record["trigger"] == "new_work_session_created"
    assert record["policy_fingerprint"] == "sha256:policy123"
    assert record["launcher"] == "governance_runtime.entrypoints.new_work_session"
    assert record["timestamps"]["materialized_at"] == "2026-03-10T12:00:00Z"


def test_archive_writes_structured_provenance_context_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-prov-ctx",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
        "model_context": {
            "provider": "openai",
            "model": "gpt-5.3-codex",
        },
        "approval_context": {
            "status": "approved",
            "initiator_role": "operator",
            "approver_role": "approver",
        },
        "ci_job_ref": "https://example.invalid/ci/123",
        "correlation_id": "corr-123",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-prov-ctx",
        observed_at="2026-03-11T11:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record_path = run_dir(workspaces_home, fingerprint, "run-prov-ctx") / "provenance-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert isinstance(record.get("model_context"), dict)
    assert record["model_context"]["model"] == "gpt-5.3-codex"
    assert isinstance(record.get("approval_context"), dict)
    assert record["approval_context"]["status"] == "approved"
    assert record["ci_job_ref"] == "https://example.invalid/ci/123"
    assert record["correlation_id"] == "corr-123"
