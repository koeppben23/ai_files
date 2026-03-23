from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_evidence_index_with_refs_and_archived_map(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-evidence-index",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "evidence_refs": ["docs/spec.md:10", "tests/test_x.py:5"],
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-evidence-index",
        observed_at="2026-03-11T13:03:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    record = json.loads((run_dir(workspaces_home, fingerprint, "run-evidence-index") / "evidence-index.json").read_text(encoding="utf-8"))
    assert record["schema"] == "governance.evidence-index.v1"
    assert record["evidence_refs"] == ["docs/spec.md:10", "tests/test_x.py:5"]
    assert isinstance(record["archived_files"], dict)
    assert record["archived_files"]["session_state"] is True
