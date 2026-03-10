from __future__ import annotations

import hashlib
import json
from pathlib import Path

from governance.infrastructure.io_verify import verify_run_archive
from governance.infrastructure.work_run_archive import archive_active_run


def _recompute_checksums(run_root: Path) -> None:
    files = {}
    for name in [
        "SESSION_STATE.json",
        "metadata.json",
        "run-manifest.json",
        "provenance-record.json",
    ]:
        files[name] = "sha256:" + hashlib.sha256((run_root / name).read_bytes()).hexdigest()
    payload = {"schema": "governance.run-checksums.v1", "files": files}
    (run_root / "checksums.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_verify_rejects_finalized_run_without_finalization_reason(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {"session_run_id": "run-meta", "Phase": "6-PostFlight", "active_gate": "Post Flight", "Next": "6"}

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-meta",
        observed_at="2026-03-10T13:30:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    run_root = workspaces_home / fingerprint / "runs" / "run-meta"
    metadata = json.loads((run_root / "metadata.json").read_text(encoding="utf-8"))
    metadata.pop("finalization_reason", None)
    (run_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True), encoding="utf-8")
    _recompute_checksums(run_root)

    ok, _, message = verify_run_archive(run_root)
    assert ok is False
    assert isinstance(message, str)
    assert "finalization_reason" in message
