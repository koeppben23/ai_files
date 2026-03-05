from __future__ import annotations

from pathlib import Path

import pytest

from tests.util import REPO_ROOT


@pytest.mark.governance
def test_plugin_artifact_exists_in_governance_artifacts() -> None:
    path = REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
    assert path.exists(), "global JS plugin artifact must exist"


@pytest.mark.governance
def test_plugin_uses_node_builtins_and_spawn_args_array() -> None:
    path = REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
    content = path.read_text(encoding="utf-8")

    assert "from \"node:child_process\"" in content
    assert "spawn(" in content
    assert "exec(" not in content
    assert '"-m"' in content
    assert '"governance.entrypoints.new_work_session"' in content
    assert '"--trigger-source"' in content
    assert '"desktop-plugin"' in content


@pytest.mark.governance
def test_plugin_listens_only_to_session_created_and_handles_field_variants() -> None:
    path = REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
    content = path.read_text(encoding="utf-8")

    assert "event.type !== \"session.created\"" in content
    assert "event.session_id" in content
    assert "event.sessionId" in content
    assert "event.id" in content
    assert "event.repo_root" in content
    assert "event.repoRoot" in content
    assert "process.cwd()" in content
