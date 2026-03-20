from __future__ import annotations

import json
import sys
from pathlib import Path

from governance_runtime.kernel.phase_kernel import RuntimeContext, execute
from tests.util import get_phase_api_path


def _prepare_binding(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    workspaces_home = cfg / "workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "pythonCommand": sys.executable,
        },
    }
    (config_root / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    (commands_home / "phase_api.yaml").write_text(get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return workspaces_home, "88b39b036804c534a1b2c3d4"


def test_missing_exit_evidence_blocks_without_completed_event(tmp_path: Path, monkeypatch) -> None:
    workspaces_home, fp = _prepare_binding(tmp_path, monkeypatch)
    state = {
        "SESSION_STATE": {
            "RepoFingerprint": fp,
            "phase": "1.3-RulebookLoad",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            # Missing LoadedRulebooks.core / RulebookLoadEvidence.core => must block
            "AddonsEvidence": {},
        }
    }

    result = execute(
        current_token="1.3",
        session_state_doc=state,
        runtime_ctx=RuntimeContext(
            requested_active_gate="Rulebook Load Gate",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            live_repo_fingerprint=fp,
        ),
    )

    assert result.status == "BLOCKED"
    events_file = workspaces_home / fp / "events.jsonl"
    lines = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    assert any(evt.get("event") == "PHASE_BLOCKED" for evt in lines)
    assert not any(evt.get("event") == "PHASE_COMPLETED" and evt.get("phase_token") == "1.3" for evt in lines)
