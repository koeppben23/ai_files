from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.entrypoints import implement_start as entrypoint
from governance.contracts.enforcement import EnforcementResult, FAIL_CLOSED_MISSING_CONTRACT


@pytest.fixture(autouse=True)
def _mock_llm_and_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "ok": True,
            "reason_code": "",
            "message": "",
            "changed_files": [],
            "llm_step_executed": True,
            "executor_command": "mock-llm",
        },
    )
    monkeypatch.setattr(
        entrypoint,
        "_run_targeted_checks",
        lambda _repo_root, _requirements: {
            "ok": True,
            "reason_code": "",
            "message": "",
            "executed": ["tests/mock_acceptance.py::test_mock"],
            "failed": [],
            "return_code": 0,
        },
    )
    monkeypatch.setattr(entrypoint, "_git_path_visible_in_status", lambda _root, _rel: True)


def _write_session(
    path: Path,
    *,
    decision: str = "approve",
    active_gate: str = "Workflow Complete",
    plan_record_versions: int = 2,
) -> None:
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "active_gate": active_gate,
            "workflow_complete": decision == "approve",
            "WorkflowComplete": decision == "approve",
            "UserReviewDecision": {
                "decision": decision,
            },
            "plan_record_versions": plan_record_versions,
            "requirement_contracts_present": True,
            "requirement_contracts_count": 3,
            "Ticket": "Move workspaces/<fp>/runs to workspaces/governance-records/<fp>/runs and keep active session under workspaces/<fp>/.",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _write_compiled_contracts(path: Path, *, hotspot: str) -> None:
    payload = {
        "schema": "governance-compiled-requirements.v1",
        "requirements": [
            {
                "id": "R-PLAN-001-aaaa1111",
                "title": "Store archived runs only under governance-records",
                "code_hotspots": [hotspot],
                "acceptance_tests": ["tests/test_archive_paths.py::test_archive_root"],
            }
        ],
        "negative_contracts": [],
        "verification_seed": [],
        "completion_seed": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _write_plan_record(path: Path) -> None:
    payload = {
        "status": "active",
        "versions": [
            {"version": 1, "plan_record_text": "Initial plan"},
            {"version": 2, "plan_record_text": "Approved plan summary"},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_main_happy_implement_start(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan_record(tmp_path / "plan-record.json")
    target = tmp_path / "service.py"
    target.write_text("RUNS_DIR = 'workspaces/<fp>/runs'\ndef run():\n    return RUNS_DIR\n", encoding="utf-8")
    _write_compiled_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json", hotspot="service.py")

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["implementation_started"] is True
    assert out["active_gate"] == "Implementation Review Complete"
    assert out["implementation_quality_stable"] is True
    assert out["implementation_changed_files"]
    assert "service.py" in "\n".join(out["implementation_changed_files"])
    assert "service.py" in "\n".join(out["implementation_semantic_changed_files"])
    assert out["implementation_llm_step_executed"] is True
    assert out["implementation_checks_ok"] is True
    assert out["next_action"] == "run /continue."
    assert "Implementation Self Review" in out["implementation_substate_history"]
    assert "Implementation Verification" in out["implementation_substate_history"]
    persisted = json.loads(session_path.read_text(encoding="utf-8"))
    ss = persisted["SESSION_STATE"]
    assert ss["implementation_authorized"] is True
    assert ss["implementation_started"] is True
    assert ss["active_gate"] == "Implementation Review Complete"
    assert ss["implementation_package_presented"] is True
    assert (tmp_path / ".governance" / "implementation" / "execution_patch.py").exists()


def test_main_bad_without_approve(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path, decision="changes_requested", active_gate="Rework Clarification Gate")
    _write_plan_record(tmp_path / "plan-record.json")

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"


def test_main_bad_blocks_when_llm_executor_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan_record(tmp_path / "plan-record.json")
    target = tmp_path / "service.py"
    target.write_text("RUNS_DIR = 'workspaces/<fp>/runs'\ndef run():\n    return RUNS_DIR\n", encoding="utf-8")
    _write_compiled_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json", hotspot="service.py")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))
    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "ok": False,
            "reason_code": "IMPLEMENTATION-LLM-EXECUTOR-FAILED",
            "message": "executor crashed",
            "changed_files": [],
            "llm_step_executed": True,
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["reason_code"] == "IMPLEMENTATION-LLM-EXECUTOR-FAILED"


def test_main_bad_missing_plan_record(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path, plan_record_versions=0)

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"


def test_main_blocked_when_forced_blocker_marker(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_compiled_contracts(
        tmp_path / ".governance" / "contracts" / "compiled_requirements.json",
        hotspot="service.py",
    )
    (tmp_path / "service.py").write_text(
        "RUNS_DIR = 'workspaces/<fp>/runs'\ndef run():\n    return RUNS_DIR\n",
        encoding="utf-8",
    )
    payload = {
        "status": "active",
        "versions": [
            {
                "version": 1,
                "plan_record_text": "Approved execution plan [[force-implementation-blocker]]",
            }
        ],
    }
    (tmp_path / "plan-record.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 2
    assert out["status"] == "blocked"
    assert out["active_gate"] == "Implementation Blocked"
    assert out["implementation_quality_stable"] is False
    assert out["implementation_open_findings"]
    assert out["reason_code"]
    assert "resolve implementation blockers" in out["next_action"]


def test_main_corner_applies_target_patch_when_plan_mentions_file(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    target = tmp_path / "service.py"
    target.write_text("RUNS_DIR = 'workspaces/<fp>/runs'\ndef run():\n    return RUNS_DIR\n", encoding="utf-8")
    payload = {
        "status": "active",
        "versions": [
            {
                "version": 1,
                "plan_record_text": "Update service.py and apply first implementation step",
            }
        ],
    }
    (tmp_path / "plan-record.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    _write_compiled_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json", hotspot="service.py")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["status"] == "ok"
    assert "service.py" in "\n".join(out["implementation_changed_files"])
    assert "governance-records/<fp>/runs" in target.read_text(encoding="utf-8")


def test_main_edge_blocks_stub_only_changes_without_domain_files(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan_record(tmp_path / "plan-record.json")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["active_gate"] == "Implementation Blocked"
    assert any("IMPLEMENTATION-NON_DOMAIN-CHANGES" in item for item in out["implementation_open_findings"])


def test_main_bad_blocks_when_targets_already_marked_and_artifact_unchanged(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan_record(tmp_path / "plan-record.json")
    target = tmp_path / "service.py"
    target.write_text(
        "def run():\n    return True\n# governance-implement: approved-plan execution touched this file\n",
        encoding="utf-8",
    )
    _write_compiled_contracts(
        tmp_path / ".governance" / "contracts" / "compiled_requirements.json",
        hotspot="service.py",
    )

    compiled = entrypoint._load_compiled_requirements(session_path, json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"])
    titles = [str(req.get("title") or "") for req in compiled]
    work_queue = entrypoint._build_execution_work_queue(
        entrypoint._latest_plan_text(tmp_path / "plan-record.json"),
        json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"],
        titles,
    )
    entrypoint._write_execution_code_artifact(tmp_path, entrypoint._latest_plan_text(tmp_path / "plan-record.json"), work_queue)

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["active_gate"] == "Implementation Blocked"
    assert any("IMPLEMENTATION-NO-CHANGES" in item for item in out["implementation_open_findings"])


def test_main_bad_blocks_when_domain_changes_not_visible_in_git_status(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan_record(tmp_path / "plan-record.json")
    target = tmp_path / "service.py"
    target.write_text("RUNS_DIR = 'workspaces/<fp>/runs'\ndef run():\n    return RUNS_DIR\n", encoding="utf-8")
    _write_compiled_contracts(
        tmp_path / ".governance" / "contracts" / "compiled_requirements.json",
        hotspot="service.py",
    )

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))
    monkeypatch.setattr(entrypoint, "_git_path_visible_in_status", lambda _root, _rel: False)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["active_gate"] == "Implementation Blocked"
    assert any("IMPLEMENTATION-NOT-VISIBLE-IN-GIT-STATUS" in item for item in out["implementation_open_findings"])


def test_main_bad_missing_compiled_contracts_blocks(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    payload["SESSION_STATE"]["requirement_contracts_present"] = False
    payload["SESSION_STATE"]["requirement_contracts_count"] = 0
    session_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    _write_plan_record(tmp_path / "plan-record.json")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))
    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert "compiled requirement contracts" in out["message"]


def test_main_bad_fail_closed_when_required_contracts_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan_record(tmp_path / "plan-record.json")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))
    monkeypatch.setattr(
        entrypoint,
        "require_complete_contracts",
        lambda repo_root, required_ids: EnforcementResult(
            ok=False,
            reason=FAIL_CLOSED_MISSING_CONTRACT,
            details=("missing_required_contract:R-IMPLEMENT-001",),
        ),
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 2
    assert out["status"] == "error"
    assert FAIL_CLOSED_MISSING_CONTRACT in out["message"]
