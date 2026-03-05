from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.application.use_cases.audit_readout_builder import build_audit_readout
from governance.engine.canonical_json import canonical_json_hash


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _setup_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    workspace = config_root / "workspaces" / "fp"
    commands_home.mkdir(parents=True)
    workspace.mkdir(parents=True)

    pointer = {
        "schema": "opencode-session-pointer.v1",
        "activeSessionStateFile": str(workspace / "SESSION_STATE.json"),
    }
    _write_json(config_root / "SESSION_STATE.json", pointer)
    return commands_home, config_root, workspace


def test_happy_build_audit_readout(tmp_path: Path) -> None:
    commands_home, _, workspace = _setup_workspace(tmp_path)

    session_state = {
        "SESSION_STATE": {
            "session_run_id": "work-2",
            "Phase": "4",
            "Next": "5",
            "active_gate": "Ticket Input Gate",
            "phase4_intake_updated_at": "2026-03-05T20:34:32Z",
        }
    }
    _write_json(workspace / "SESSION_STATE.json", session_state)

    snapshot = {
        "schema": "governance.work-run.snapshot.v1",
        "archived_at": "2026-03-05T20:30:00Z",
        "repo_fingerprint": "fp",
        "session_run_id": "work-1",
        "source_phase": "6-PostFlight",
        "source_active_gate": "Post Flight",
        "source_next": "6",
        "ticket_digest": None,
        "task_digest": None,
        "plan_record_digest": None,
        "impl_digest": None,
        "session_state": {"Phase": "6-PostFlight"},
    }
    snapshot_path = workspace / "work_runs" / "work-1.json"
    _write_json(snapshot_path, snapshot)
    snapshot_digest = canonical_json_hash(snapshot)

    events_path = workspace / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "new_work_session_created",
                        "observed_at": "2026-03-05T20:34:32Z",
                        "repo_fingerprint": "fp",
                        "session_id": "sess-1",
                        "run_id": "work-1",
                        "new_run_id": "work-2",
                        "snapshot_path": str(snapshot_path),
                        "snapshot_digest": snapshot_digest,
                        "phase": "4",
                        "next": "5",
                    }
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    assert payload["contract_version"] == "AUDIT_READOUT_SPEC.v1"
    assert payload["active"]["run_id"] == "work-2"
    assert payload["last_snapshot"]["snapshot_digest"] == snapshot_digest
    assert payload["integrity"]["snapshot_ref_present"] is True
    assert payload["integrity"]["run_id_consistent"] is True
    assert payload["integrity"]["monotonic_timestamps"] is True


def test_bad_created_event_missing_snapshot_ref_raises(tmp_path: Path) -> None:
    commands_home, _, workspace = _setup_workspace(tmp_path)

    _write_json(
        workspace / "SESSION_STATE.json",
        {
            "SESSION_STATE": {
                "session_run_id": "work-2",
                "Phase": "4",
                "Next": "5",
                "active_gate": "Ticket Input Gate",
                "phase4_intake_updated_at": "2026-03-05T20:34:32Z",
            }
        },
    )
    _write_json(
        workspace / "work_runs" / "work-1.json",
        {
            "schema": "governance.work-run.snapshot.v1",
            "archived_at": "2026-03-05T20:30:00Z",
            "repo_fingerprint": "fp",
            "session_run_id": "work-1",
            "source_phase": "6-PostFlight",
            "source_active_gate": "Post Flight",
            "source_next": "6",
            "ticket_digest": None,
            "task_digest": None,
            "plan_record_digest": None,
            "impl_digest": None,
            "session_state": {"Phase": "6-PostFlight"},
        },
    )
    (workspace / "events.jsonl").write_text(
        json.dumps(
            {
                "event": "new_work_session_created",
                "observed_at": "2026-03-05T20:34:32Z",
                "repo_fingerprint": "fp",
                "session_id": "sess-1",
                "run_id": "work-1",
                "new_run_id": "work-2",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid audit readout contract"):
        build_audit_readout(commands_home=commands_home)


def test_replay_determinism_same_input_same_output(tmp_path: Path) -> None:
    commands_home, _, workspace = _setup_workspace(tmp_path)

    _write_json(
        workspace / "SESSION_STATE.json",
        {
            "SESSION_STATE": {
                "session_run_id": "work-7",
                "Phase": "5",
                "Next": "5.3",
                "active_gate": "Architecture Review Gate",
                "phase4_intake_updated_at": "2026-03-05T20:40:00Z",
            }
        },
    )
    snapshot = {
        "schema": "governance.work-run.snapshot.v1",
        "archived_at": "2026-03-05T20:39:00Z",
        "repo_fingerprint": "fp",
        "session_run_id": "work-6",
        "source_phase": "5-ArchitectureReview",
        "source_active_gate": "Architecture Review Gate",
        "source_next": "5.3",
        "ticket_digest": None,
        "task_digest": None,
        "plan_record_digest": None,
        "impl_digest": None,
        "session_state": {"Phase": "5"},
    }
    snapshot_path = workspace / "work_runs" / "work-6.json"
    _write_json(snapshot_path, snapshot)
    digest = canonical_json_hash(snapshot)
    (workspace / "events.jsonl").write_text(
        json.dumps(
            {
                "event": "new_work_session_created",
                "observed_at": "2026-03-05T20:40:00Z",
                "repo_fingerprint": "fp",
                "session_id": "sess-1",
                "run_id": "work-6",
                "new_run_id": "work-7",
                "snapshot_path": str(snapshot_path),
                "snapshot_digest": digest,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    first = build_audit_readout(commands_home=commands_home)
    second = build_audit_readout(commands_home=commands_home)
    assert first == second
