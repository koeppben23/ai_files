from __future__ import annotations

import json
from pathlib import Path

from governance.entrypoints import review_decision_persist as entrypoint


def _write_session(path: Path, *, phase: str = "6-PostFlight") -> None:
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "Phase": phase,
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
                "P5.6-RollbackSafety": "approved",
            },
            "ImplementationReview": {
                "implementation_review_complete": True,
            },
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

    rc = entrypoint.main(["--decision", "approve", "--note", "ok", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["decision"] == "approve"
    assert events_path.exists()


def test_main_bad_invalid_decision(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main(["--decision", "invalid", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert out["reason_code"] == "BLOCKED-REVIEW-DECISION-INVALID"


def test_main_corner_changes_requested(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    monkeypatch.setattr(
        entrypoint,
        "_resolve_active_session_path",
        lambda: (session_path, events_path),
    )

    rc = entrypoint.main(["--decision", "changes_requested", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["decision"] == "changes_requested"


def test_main_edge_resolver_failure_returns_error(monkeypatch, capsys) -> None:
    def _boom() -> tuple[Path, Path]:
        raise RuntimeError("pointer missing")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", _boom)
    rc = entrypoint.main(["--decision", "approve", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert out["reason_code"] == "BLOCKED-REVIEW-DECISION-INVALID"
