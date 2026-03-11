from __future__ import annotations

import json
from pathlib import Path

from governance.entrypoints import implement_start as entrypoint


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
        },
    }
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
    persisted = json.loads(session_path.read_text(encoding="utf-8"))
    ss = persisted["SESSION_STATE"]
    assert ss["implementation_authorized"] is True
    assert ss["implementation_started"] is True
    assert ss["active_gate"] == "Implementation Started"


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
