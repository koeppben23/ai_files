from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.entrypoints import verify_contracts as entrypoint


def _write_session(path: Path) -> None:
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "phase": "6-PostFlight",
            "active_gate": "Implementation Presentation Gate",
            "session_run_id": "sess-1",
            "session_materialization_event_id": "mat-1",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_main_happy_persists_completion_matrix(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    workspace_dir = tmp_path
    _write_session(session_path)

    monkeypatch.setattr(
        entrypoint,
        "resolve_active_session_paths",
        lambda: (session_path, "fingerprint", workspace_dir, workspace_dir)
    )
    monkeypatch.setattr(
        entrypoint,
        "run_contract_verification",
        lambda repo_root: {
            "status": "PASS",
            "merge_allowed": True,
            "merge_reason": "merge_allowed",
            "matrix": {
                "completion_matrix": [],
                "overall_status": "PASS",
                "release_blocking_requirements_failed": [],
                "release_blocking_requirements_unverified": [],
            },
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["status"] == "ok"

    state_doc = json.loads(session_path.read_text(encoding="utf-8"))
    state = state_doc["SESSION_STATE"]
    assert state["completion_matrix_overall_status"] == "PASS"
    assert state["completion_matrix_receipt"]["receipt_type"] == "verification_receipt"


def test_main_bad_blocks_when_verification_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    workspace_dir = tmp_path
    _write_session(session_path)

    monkeypatch.setattr(
        entrypoint,
        "resolve_active_session_paths",
        lambda: (session_path, "fingerprint", workspace_dir, workspace_dir)
    )
    monkeypatch.setattr(
        entrypoint,
        "run_contract_verification",
        lambda repo_root: {
            "status": "FAIL",
            "merge_allowed": False,
            "merge_reason": "overall_status=FAIL",
            "matrix": {
                "completion_matrix": [],
                "overall_status": "FAIL",
                "release_blocking_requirements_failed": ["R-1"],
                "release_blocking_requirements_unverified": [],
            },
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 2
    assert out["status"] == "blocked"
