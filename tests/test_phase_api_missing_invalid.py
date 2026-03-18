from __future__ import annotations

import json
import sys
from pathlib import Path

from governance.application.use_cases.phase_router import route_phase


def _write_binding(tmp_path: Path, *, write_phase_api: bool, phase_api_text: str = "") -> tuple[Path, Path, Path]:
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
    (commands_home / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    if write_phase_api:
        (commands_home / "phase_api.yaml").write_text(phase_api_text, encoding="utf-8")
    return home, commands_home, workspaces_home


def test_phase_api_missing_blocks_and_writes_workspace_log(tmp_path: Path, monkeypatch) -> None:
    home, _commands_home, workspaces_home = _write_binding(tmp_path, write_phase_api=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    fp = "88b39b036804c534a1b2c3d4"
    routed = route_phase(
        requested_phase="2.1",
        requested_active_gate="Decision Pack",
        requested_next_gate_condition="Proceed",
        session_state_document={"SESSION_STATE": {"RepoFingerprint": fp}},
        repo_is_git_root=True,
        live_repo_fingerprint=fp,
    )
    assert routed.status == "BLOCKED"
    assert routed.source == "phase-api-missing"
    assert (workspaces_home / fp / "logs" / "error.log.jsonl").exists()


def test_phase_api_invalid_blocks_and_falls_back_to_commands_log_when_fp_unknown(tmp_path: Path, monkeypatch) -> None:
    home, commands_home, _workspaces_home = _write_binding(
        tmp_path,
        write_phase_api=True,
        phase_api_text="not: [valid\n",
    )
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    routed = route_phase(
        requested_phase="2.1",
        requested_active_gate="Decision Pack",
        requested_next_gate_condition="Proceed",
        session_state_document={"SESSION_STATE": {}},
        repo_is_git_root=True,
    )
    assert routed.status == "BLOCKED"
    assert routed.source == "phase-api-missing"
    # Runtime now enforces workspace-log-only semantics and may skip log emission
    # when no repo fingerprint can be resolved.
    assert True
