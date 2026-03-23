from __future__ import annotations

import json
import sys
from pathlib import Path

from governance_runtime.application.use_cases.phase_router import route_phase


def _write_binding(tmp_path: Path, *, write_phase_api: bool, phase_api_text: str = "", monkeypatch=None) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    workspaces_home = cfg / "workspaces"
    spec_home = cfg / "governance_spec"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "specHome": str(spec_home),
            "pythonCommand": sys.executable,
        },
    }
    (cfg / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    if write_phase_api:
        (spec_home / "phase_api.yaml").write_text(phase_api_text, encoding="utf-8")
    if monkeypatch is not None:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cfg))
    return home, commands_home, workspaces_home


def test_phase_api_missing_blocks(tmp_path: Path, monkeypatch) -> None:
    home, _commands_home, _workspaces_home = _write_binding(tmp_path, write_phase_api=False, monkeypatch=monkeypatch)
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


def test_commands_phase_api_yaml_alone_is_not_authority(tmp_path: Path, monkeypatch) -> None:
    """commands/phase_api.yaml must NOT be accepted as authority.

    Contract: commands/ contains only rails.  Even if a phase_api.yaml is
    physically present under commands/, the resolver must block when
    specHome/phase_api.yaml is missing.
    """
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    spec_home = cfg / "governance_spec"
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    # Write a VALID yaml to commands_home (should NOT be used)
    (commands_home / "phase_api.yaml").write_text(
        'version: 1\nstart_token: "1.1"\nphases:\n  - token: "1.1"\n    phase: "1.1-Bootstrap"\n    active_gate: "G"\n    next_gate_condition: "N"\n    next: "2"\n  - token: "2"\n    phase: "2-Discovery"\n    active_gate: "G"\n    next_gate_condition: "N"\n',
        encoding="utf-8",
    )
    # Do NOT write anything to spec_home — it stays empty
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(cfg / "workspaces"),
            "specHome": str(spec_home),
            "pythonCommand": sys.executable,
        },
    }
    (cfg / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cfg))

    routed = route_phase(
        requested_phase="2.1",
        requested_active_gate="Decision Pack",
        requested_next_gate_condition="Proceed",
        session_state_document={"SESSION_STATE": {}},
        repo_is_git_root=True,
    )
    assert routed.status == "BLOCKED"
    assert routed.source == "phase-api-missing"


def test_phase_api_invalid_blocks(tmp_path: Path, monkeypatch) -> None:
    home, commands_home, _workspaces_home = _write_binding(
        tmp_path,
        write_phase_api=True,
        phase_api_text="not: [valid\n",
        monkeypatch=monkeypatch,
    )
    routed = route_phase(
        requested_phase="2.1",
        requested_active_gate="Decision Pack",
        requested_next_gate_condition="Proceed",
        session_state_document={"SESSION_STATE": {}},
        repo_is_git_root=True,
    )
    assert routed.status == "BLOCKED"
    assert routed.source == "phase-api-missing"
