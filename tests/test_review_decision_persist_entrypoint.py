from __future__ import annotations

import json
import hashlib
from pathlib import Path

from governance.entrypoints import review_decision_persist as entrypoint


def _write_session(path: Path, *, phase: str = "6-PostFlight") -> None:
    review_object = "Final Phase-6 implementation review decision"
    digest_source = "|".join(
        [
            review_object,
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "Phase": phase,
            "active_gate": "Evidence Presentation Gate",
            "session_materialization_event_id": "mat-abc",
            "session_materialized_at": "2026-03-12T00:00:00Z",
            "session_run_id": "sess-abc",
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
            "implementation_review_complete": True,
            "review_package_presented": True,
            "review_package_plan_body_present": True,
            "review_package_review_object": review_object,
            "review_package_last_state_change_at": "2026-03-12T00:00:00Z",
            "review_package_presentation_receipt": {
                "receipt_type": "governance_review_presentation_receipt",
                "requirement_scope": "R-REVIEW-DECISION-001",
                "content_digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
                "rendered_at": "2026-03-12T00:00:01Z",
                "render_event_id": "mat-abc",
                "gate": "Evidence Presentation Gate",
                "session_id": "sess-abc",
                "state_revision": "mat-abc",
                "source_command": "/continue",
                "digest": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
                "presented_at": "2026-03-12T00:00:00Z",
                "contract": "guided-ui.v1",
                "materialization_event_id": "mat-abc",
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


def test_main_bad_stale_receipt_timestamp_blocks(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)

    payload = json.loads(session_path.read_text(encoding="utf-8"))
    payload["SESSION_STATE"]["review_package_presentation_receipt"]["rendered_at"] = "2026-03-11T23:59:59Z"
    session_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))
    rc = entrypoint.main(["--decision", "approve", "--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert "BLOCKED-RECEIPT-STALE-TIMESTAMP" in out["message"]


def test_main_bad_missing_decision_argument_raises_system_exit() -> None:
    try:
        entrypoint.main(["--quiet"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse SystemExit for missing --decision")
