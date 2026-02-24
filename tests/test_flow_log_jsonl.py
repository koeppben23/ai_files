from __future__ import annotations

import json
from pathlib import Path

from governance.kernel.phase_kernel import RuntimeContext, execute


def _write_phase_api(commands_home: Path) -> None:
    repo_spec = Path(__file__).resolve().parents[1] / "phase_api.yaml"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(repo_spec.read_text(encoding="utf-8"), encoding="utf-8")


def test_kernel_writes_flow_and_workspace_events(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    workspaces_home = tmp_path / "workspaces"
    _write_phase_api(commands_home)

    doc = {
        "SESSION_STATE": {
            "RepoFingerprint": "88b39b036804c534a1b2c3d4",
            "Phase": "3B-1",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "LoadedRulebooks": {"core": "${COMMANDS_HOME}/master.md"},
        }
    }

    result = execute(
        current_token="3B-1",
        session_state_doc=doc,
        runtime_ctx=RuntimeContext(
            requested_active_gate="API Logical Validation",
            requested_next_gate_condition="Continue",
            repo_is_git_root=True,
            commands_home=commands_home,
            workspaces_home=workspaces_home,
            config_root=tmp_path / "cfg",
        ),
    )

    assert result.status == "OK"
    flow_path = commands_home / "logs" / "flow.log.jsonl"
    workspace_events = workspaces_home / "88b39b036804c534a1b2c3d4" / "events.jsonl"
    assert flow_path.exists()
    assert workspace_events.exists()
    assert json.loads(flow_path.read_text(encoding="utf-8").splitlines()[-1])["event"] == "PHASE_COMPLETED"
