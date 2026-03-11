from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.entrypoints.human_approval_persist import apply_human_approval
from governance.infrastructure.workspace_paths import run_dir
from governance.infrastructure.work_run_archive import archive_active_run


def _write_session_state(path: Path) -> dict[str, object]:
    state = {
        "session_run_id": "run-human-approval",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "PullRequestTitle": "feat: regulated human approval",
        "PullRequestBody": "body",
        "regulated_mode_state": "active",
    }
    path.write_text(
        json.dumps({"schema": "opencode-session-state.v1", "SESSION_STATE": state}, ensure_ascii=True),
        encoding="utf-8",
    )
    return state


def test_human_approval_approved_allows_regulated_finalization(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session_state(session_path)

    result = apply_human_approval(
        decision="approve",
        session_path=session_path,
        initiator_role="operator",
        approver_role="approver",
        events_path=events_path,
        rationale="reviewed by second pair of eyes",
    )
    assert result["status"] == "ok"

    session_doc = json.loads(session_path.read_text(encoding="utf-8"))
    state = session_doc["SESSION_STATE"]
    assert state["approval_status"] == "approved"

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-human-approval",
        observed_at="2026-03-11T14:20:00Z",
        session_state_document=session_doc,
        state_view=state,
    )

    run_root = run_dir(workspaces_home, fingerprint, "run-human-approval")
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    pr_record = json.loads((run_root / "pr-record.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "finalized"
    assert pr_record["requires_human_approval"] is True
    assert pr_record["approval_status"] == "approved"


def test_human_approval_rejected_blocks_regulated_finalization(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    session_path = tmp_path / "SESSION_STATE.json"
    _write_session_state(session_path)

    result = apply_human_approval(
        decision="reject",
        session_path=session_path,
        initiator_role="operator",
        approver_role="approver",
        rationale="changes requested",
    )
    assert result["status"] == "ok"

    session_doc = json.loads(session_path.read_text(encoding="utf-8"))
    state = session_doc["SESSION_STATE"]

    with pytest.raises(RuntimeError):
        archive_active_run(
            workspaces_home=workspaces_home,
            repo_fingerprint=fingerprint,
            run_id="run-human-approval",
            observed_at="2026-03-11T14:21:00Z",
            session_state_document=session_doc,
            state_view=state,
        )

    run_root = run_dir(workspaces_home, fingerprint, "run-human-approval")
    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "failed"
    errors = manifest.get("finalization_errors")
    assert isinstance(errors, list)
    assert any("approved human approval" in str(item) for item in errors)
