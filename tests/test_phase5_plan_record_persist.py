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
    assert state["PlanRecordVersions"] >= 1
    assert state["phase5_completed"] is True
    assert state["self_review_iterations_met"] is True
    assert state["phase5_self_review_iterations"] >= 1
    assert state["phase5_state"] == "phase5_completed"
    assert state["phase5_blocker_code"] == "none"
    assert state["requirement_contracts_present"] is True
    assert int(state["requirement_contracts_count"]) >= 1
    assert str(state["requirement_contracts_digest"]).startswith("sha256:")
    assert Path(str(state["requirement_contracts_source"])).exists()

    plan_record = json.loads((session_path.parent / "plan-record.json").read_text(encoding="utf-8"))
    assert plan_record["status"] == "active"
    assert len(plan_record["versions"]) >= 1
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
    assert state["PlanRecordVersions"] >= 1
    assert state["phase5_completed"] is True
    assert state["self_review_iterations_met"] is True
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
def test_phase5_plan_persist_bad_missing_ticket_evidence_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    state.pop("TicketRecordDigest", None)
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Architecture plan", "--quiet"])
    assert rc == 2
    blocked = json.loads(capsys.readouterr().out.strip())
    assert blocked["reason_code"] == "BLOCKED-P5-TICKET-EVIDENCE-MISSING"
    assert blocked["reason"] == "missing-ticket-intake-evidence"


@pytest.mark.governance
def test_phase5_plan_persist_bad_outside_phase5_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    payload["SESSION_STATE"]["Phase"] = "4"
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "Architecture plan", "--quiet"])
    assert rc == 2
    blocked = json.loads(capsys.readouterr().out.strip())
    assert blocked["reason_code"] == "BLOCKED-P5-PHASE-MISMATCH"
    assert blocked["reason"] == "phase5-plan-persist-not-allowed-outside-phase5"


@pytest.mark.governance
def test_phase5_plan_persist_happy_consumes_rework_clarification_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    state["Phase"] = "6-PostFlight"
    state["phase"] = "6-PostFlight"
    state["active_gate"] = "Rework Clarification Gate"
    state["phase6_state"] = "phase6_changes_requested"
    state["next_gate_condition"] = "Clarify requested changes in chat, then run directed next rail."
    state["UserReviewDecision"] = {"decision": "changes_requested"}
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main([
        "--plan-text",
        "## Zielbild\n## Soll-Flow\n## State-Machine\n## Blocker-Taxonomie\n## Audit\n## Go/No-Go\nReason code",
        "--quiet",
    ])
    assert rc == 0

    updated = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
    assert updated["active_gate"] != "Rework Clarification Gate"
    assert updated.get("phase6_state") != "phase6_changes_requested"
    assert updated.get("UserReviewDecision") is None
    assert updated["rework_clarification_consumed"] is True
    assert updated["rework_clarification_consumed_by"] == "plan"


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
def test_phase5_plan_persist_corner_force_drift_reaches_max_iterations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "## Zielbild\n[[force-drift]]", "--quiet"])
    assert rc == 0

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    state = payload["SESSION_STATE"]
    assert state["phase5_self_review_iterations"] == 3
    assert state["phase5_revision_delta"] == "changed"
    assert state["self_review_iterations_met"] is True


@pytest.mark.governance
def test_phase5_plan_persist_happy_writes_iteration_audit_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    config_root, commands_home, session_path, _ = _write_fixture_state(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

    rc = module.main(["--plan-text", "## Zielbild\n## Soll-Flow\n## State-Machine\n## Blocker-Taxonomie\n## Audit\n## Go/No-Go\nReason code", "--quiet"])
    assert rc == 0

    events = (session_path.parent / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    iteration_events = [json.loads(line) for line in events if '"event":"phase5-self-review-iteration"' in line]
    assert len(iteration_events) >= 1
    row = iteration_events[0]
    assert "input_digest" in row
    assert "iteration" in row
    assert "findings_summary" in row
    assert "revision_delta" in row
    assert "plan_record_version" in row
    assert "outcome" in row
    assert "completion_status" in row


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
