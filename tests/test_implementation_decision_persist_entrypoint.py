from __future__ import annotations

import json
import hashlib
from pathlib import Path

from governance.entrypoints import implementation_decision_persist as entrypoint


def _write_session(path: Path, *, gate: str = "Implementation Presentation Gate", open_findings: list[str] | None = None) -> None:
    changed_files = [".governance/implementation/execution_patch.py"]
    findings_open = open_findings or []
    digest_source = "|".join(
        [
            "Implemented result review",
            "latest approved plan record",
            json.dumps(changed_files, ensure_ascii=True, sort_keys=True),
            json.dumps([], ensure_ascii=True, sort_keys=True),
            json.dumps(findings_open, ensure_ascii=True, sort_keys=True),
            json.dumps([], ensure_ascii=True, sort_keys=True),
            "stable",
        ]
    )
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "Phase": "6-PostFlight",
            "active_gate": gate,
            "session_materialization_event_id": "mat-abc",
            "implementation_package_presented": True,
            "implementation_quality_stable": True,
            "implementation_package_changed_files": changed_files,
            "implementation_open_findings": findings_open,
            "implementation_package_stability": "stable",
            "implementation_package_presentation_receipt": {
                "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
                "presented_at": "2026-03-12T00:00:00Z",
                "contract": "guided-ui.v1",
                "materialization_event_id": "mat-abc",
            },
            "implementation_status": "in_progress",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_main_happy_approve(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--decision", "approve", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["decision"] == "approve"
    assert out["next_gate"] == "Implementation Accepted"


def test_main_bad_invalid_decision(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--decision", "maybe", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert "Invalid decision" in out["message"]


def test_main_bad_gate_mismatch(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path, gate="Implementation Blocked")
    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--decision", "approve", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 2
    assert out["status"] == "error"
    assert "Implementation Presentation Gate" in out["message"]


def test_main_edge_approve_blocked_by_critical_findings(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path, open_findings=["critical:IMPLEMENTATION-FOO:open issue"])
    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--decision", "approve", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 2
    assert out["status"] == "error"
    assert "critical findings remain open" in out["message"]


def test_main_happy_changes_requested_routes_rework(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))

    rc = entrypoint.main(["--decision", "changes_requested", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["status"] == "ok"
    assert out["next_gate"] == "Implementation Rework Clarification Gate"
