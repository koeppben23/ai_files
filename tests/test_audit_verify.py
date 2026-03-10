from __future__ import annotations

from pathlib import Path

from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.work_run_archive import archive_active_run


def test_verify_detects_tamper_and_incomplete_runs(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-verify", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-verify",
        observed_at="2026-03-10T10:30:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-verify"
    ok, _, message = verify_run_archive(run_root)
    assert ok is True
    assert message is None

    (run_root / "SESSION_STATE.json").write_text('{"tampered":true}', encoding="utf-8")
    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "Checksum mismatch" in message
