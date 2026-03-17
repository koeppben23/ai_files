from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from .util import REPO_ROOT, get_phase_api_path


def _load_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "phase4_intake_persist.py"
    spec = importlib.util.spec_from_file_location("phase4_intake_persist", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load phase4_intake_persist module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture_state(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    config_root = tmp_path / "cfg"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    repo_fp = "abc123def456abc123def456"
    workspace = workspaces_home / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    commands_home.mkdir(parents=True, exist_ok=True)

    (commands_home / "phase_api.yaml").write_text(get_phase_api_path().read_text(encoding="utf-8"), encoding="utf-8")

    paths = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "configRoot": str(config_root),
            "pythonCommand": "python3",
        },
    }
    (commands_home / "governance.paths.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")

    session_path = workspace / "SESSION_STATE.json"
    session = {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fp,
            "Phase": "4",
            "Next": "4",
            "active_gate": "Ticket Input Gate",
            "next_gate_condition": "Collect ticket",
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
            "Bootstrap": {"Satisfied": True},
            "ActiveProfile": "profile.fallback-minimum",
            "LoadedRulebooks": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.yml",
                "templates": "${COMMANDS_HOME}/master.md",
                "addons": {
                    "riskTiering": "${COMMANDS_HOME}/rulesets/profiles/rules.risk-tiering.yml",
                },
            },
            "RulebookLoadEvidence": {
                "core": "${COMMANDS_HOME}/rules.md",
                "profile": "${COMMANDS_HOME}/rulesets/profiles/rules.fallback-minimum.yml",
            },
            "AddonsEvidence": {
                "riskTiering": {"status": "loaded"},
            },
        }
    }
    session_path.write_text(json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    pointer = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": repo_fp,
        "activeSessionStateFile": str(session_path),
    }
    (config_root / "SESSION_STATE.json").write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    return config_root, commands_home, session_path, repo_fp


@pytest.mark.governance
def test_phase4_intake_good_chat_text_routes_to_phase5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--ticket-text", "Implement BR bridge", "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["Ticket"] == "Implement BR bridge"
    assert isinstance(state["TicketRecordDigest"], str) and state["TicketRecordDigest"]
    assert state["phase4_intake_evidence"] is True
    assert state["phase4_intake_source"] == "phase4-intake-bridge"
    assert state["Phase"] == "5-ArchitectureReview"
    assert state["active_gate"] == "Plan Record Preparation Gate"


@pytest.mark.governance
def test_phase4_intake_good_file_input_routes_to_phase5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    ticket_file = tmp_path / "ticket.md"
    ticket_file.write_text("\n\nImplement from file\n", encoding="utf-8")

    rc = module.main(["--ticket-file", str(ticket_file), "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["Ticket"] == "Implement from file"
    assert isinstance(state["TicketRecordDigest"], str) and state["TicketRecordDigest"]
    assert state["Phase"] == "5-ArchitectureReview"
    assert state["active_gate"] == "Plan Record Preparation Gate"


@pytest.mark.governance
def test_phase4_intake_edge_idempotent_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    assert module.main(["--task-text", "Do X", "--quiet"]) == 0
    first = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]["TaskRecordDigest"]
    assert module.main(["--task-text", "Do X", "--quiet"]) == 0
    second = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]["TaskRecordDigest"]
    assert first == second


@pytest.mark.governance
def test_phase4_intake_bad_missing_evidence_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    module = _load_module()
    config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--quiet"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-P4-INTAKE-MISSING-EVIDENCE"


@pytest.mark.governance
def test_phase4_intake_corner_feature_complexity_only_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    module = _load_module()
    config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(
        [
            "--feature-class",
            "STANDARD",
            "--feature-reason",
            "classified",
            "--feature-planning-depth",
            "standard",
            "--quiet",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-P4-INTAKE-MISSING-EVIDENCE"


@pytest.mark.governance
def test_phase4_intake_happy_consumes_rework_clarification_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    state["Phase"] = "6-PostFlight"
    state["active_gate"] = "Rework Clarification Gate"
    state["phase6_state"] = "phase6_changes_requested"
    state["next_gate_condition"] = "Clarify requested changes in chat, then run directed next rail."
    state["UserReviewDecision"] = {"decision": "changes_requested"}
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--ticket-text", "Reworked scope after clarification", "--quiet"])
    assert rc == 0

    updated = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
    assert updated["Phase"] == "5-ArchitectureReview"
    assert updated["active_gate"] == "Plan Record Preparation Gate"
    assert updated.get("phase6_state") is None
    assert updated.get("UserReviewDecision") is None
    assert updated["rework_clarification_consumed"] is True
    assert updated["rework_clarification_consumed_by"] == "ticket"
