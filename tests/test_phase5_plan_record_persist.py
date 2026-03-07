from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "phase5_plan_record_persist.py"
    spec = importlib.util.spec_from_file_location("phase5_plan_record_persist", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load phase5_plan_record_persist module")
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

    (commands_home / "phase_api.yaml").write_text((REPO_ROOT / "phase_api.yaml").read_text(encoding="utf-8"), encoding="utf-8")

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
            "Phase": "5-ArchitectureReview",
            "Next": "5",
            "Mode": "IN_PROGRESS",
            "session_run_id": "work-123",
            "active_gate": "Plan Record Preparation Gate",
            "next_gate_condition": "Persist plan record evidence",
            "TicketRecordDigest": "sha256:ticket-v1",
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
def test_phase5_plan_persist_good_chat_text_persists_and_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Architecture plan v1", "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["Phase"] == "5-ArchitectureReview"
    assert state["active_gate"] == "Architecture Review Gate"
    assert state["PlanRecordStatus"] == "active"
    assert state["PlanRecordVersions"] == 1

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["status"] == "active"
    assert len(plan_record["versions"]) == 1
    assert plan_record["versions"][0]["trigger"] == "phase5-plan-record-rail"


@pytest.mark.governance
def test_phase5_plan_persist_good_file_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    plan_file = tmp_path / "plan.md"
    plan_file.write_text("\n\nPlan from file\n", encoding="utf-8")

    rc = module.main(["--plan-file", str(plan_file), "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["PlanRecordVersions"] == 1
    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert "Plan from file" in plan_record["versions"][0]["plan_record_text"]


@pytest.mark.governance
def test_phase5_plan_persist_bad_missing_evidence_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--quiet"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-P5-PLAN-RECORD-PERSIST"


@pytest.mark.governance
def test_phase5_plan_persist_corner_file_input_wins_over_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    plan_file = tmp_path / "plan.md"
    plan_file.write_text("plan from file content", encoding="utf-8")

    rc = module.main([
        "--plan-text",
        "plan from text content",
        "--plan-file",
        str(plan_file),
        "--quiet",
    ])
    assert rc == 0

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["versions"][0]["plan_record_text"] == "plan from file content"


@pytest.mark.governance
def test_phase5_plan_persist_edge_canonicalizes_crlf_and_blank_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "\r\n\r\nLine A\r\nLine B\r\n\r\n", "--quiet"])
    assert rc == 0

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["versions"][0]["plan_record_text"] == "Line A\nLine B"


@pytest.mark.governance
def test_phase5_plan_persist_bad_missing_active_repo_pointer_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, _, _ = _write_fixture_state(tmp_path)
    pointer_path = config_root / "SESSION_STATE.json"
    pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer_payload["activeRepoFingerprint"] = ""
    pointer_path.write_text(json.dumps(pointer_payload, indent=2), encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Plan exists", "--quiet"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason_code"] == "BLOCKED-P5-PLAN-RECORD-PERSIST"
