from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_materializes_ticket_review_outcome_and_evidence_records(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-full-artifacts",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-full-artifacts",
        observed_at="2026-03-11T08:00:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = run_dir(workspaces_home, fingerprint, "run-full-artifacts")
    assert (run_root / "ticket-record.json").is_file()
    assert (run_root / "review-decision-record.json").is_file()
    assert (run_root / "outcome-record.json").is_file()
    assert (run_root / "evidence-index.json").is_file()
    assert (run_root / "finalization-record.json").is_file()


def test_core_artifacts_include_common_contract_header_fields(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-header-fields",
        "phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "next": "6",
        "PullRequestTitle": "feat: harden contracts",
        "PullRequestBody": "body",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-header-fields",
        observed_at="2026-03-11T08:10:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = run_dir(workspaces_home, fingerprint, "run-header-fields")
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    pr_record = json.loads((run_root / "pr-record.json").read_text(encoding="utf-8"))
    provenance = json.loads((run_root / "provenance-record.json").read_text(encoding="utf-8"))

    required_header_keys = {
        "schema_version",
        "artifact_type",
        "artifact_id",
        "run_id",
        "session_id",
        "repo_slug",
        "repo_fingerprint",
        "created_at",
        "created_by_component",
        "content_hash",
        "classification",
        "integrity_status",
    }
    assert required_header_keys.issubset(set(manifest.keys()))
    assert required_header_keys.issubset(set(pr_record.keys()))
    assert required_header_keys.issubset(set(provenance.keys()))
