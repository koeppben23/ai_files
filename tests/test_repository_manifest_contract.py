from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.infrastructure.workspace_paths import repository_manifest_path
from governance_runtime.infrastructure.work_run_archive import archive_active_run


def test_archive_writes_repository_manifest_with_required_context(tmp_path: Path) -> None:
    workspaces_home = tmp_path / "workspaces"
    fingerprint = "abc123def456abc123def456"
    state = {
        "session_run_id": "run-repository-manifest",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "remote_url": "https://example.invalid/repo.git",
        "default_branch": "main",
        "tenant_context": "default",
        "repository_classification": "internal",
    }

    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=fingerprint,
        run_id="run-repository-manifest",
        observed_at="2026-03-11T13:05:00Z",
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )

    manifest = json.loads(repository_manifest_path(workspaces_home, fingerprint).read_text(encoding="utf-8"))
    assert manifest["schema"] == "governance.repository-manifest.v1"
    assert manifest["repo_fingerprint"] == fingerprint
    assert manifest["default_branch"] == "main"
    assert manifest["tenant_context"] == "default"
    assert manifest["repository_classification"] == "internal"
    assert "canonical_remote_url_digest" in manifest
