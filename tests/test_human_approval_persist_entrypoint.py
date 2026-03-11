from __future__ import annotations

import json
from pathlib import Path

from governance.entrypoints import human_approval_persist as entrypoint


def _write_session(path: Path) -> None:
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "regulated_mode_state": "active",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_main_happy_approve(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main([
        "--decision",
        "approve",
        "--initiator-role",
        "operator",
        "--approver-role",
        "approver",
        "--quiet",
    ])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["approval_status"] == "approved"
    persisted = json.loads(session_path.read_text(encoding="utf-8"))
    state = persisted["SESSION_STATE"]
    assert state["approval_status"] == "approved"
    assert state["approver_role"] == "approver"


def test_main_bad_same_approver_rejected(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main([
        "--decision",
        "approve",
        "--initiator-role",
        "operator",
        "--approver-role",
        "operator",
        "--quiet",
    ])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert out["reason_code"] == "BLOCKED-PERMISSION-DENIED"


def test_main_edge_reset_sets_pending(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main([
        "--decision",
        "reset",
        "--initiator-role",
        "operator",
        "--approver-role",
        "approver",
        "--quiet",
    ])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["approval_status"] == "pending"


def test_main_bad_invalid_role(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)

    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main([
        "--decision",
        "approve",
        "--initiator-role",
        "operator",
        "--approver-role",
        "nobody",
        "--quiet",
    ])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert out["reason_code"] == "BLOCKED-PERMISSION-DENIED"
