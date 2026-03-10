from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pytest

from governance.application.use_cases.audit_readout_builder import build_audit_readout
from governance.domain.canonical_json import canonical_json_hash


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
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


def _write_run_archive(
    workspace: Path,
    *,
    run_id: str,
    archived_at: str,
    source_phase: str,
    state_phase: str,
) -> tuple[Path, str]:
    run_dir = workspace / "runs" / run_id
    snapshot_doc = {
        "SESSION_STATE": {
            "session_run_id": run_id,
            "Phase": state_phase,
            "active_gate": "Architecture Review Gate",
            "Next": "5.3",
        }
    }
    snapshot_path = run_dir / "SESSION_STATE.json"
    _write_json(snapshot_path, snapshot_doc)
    digest = canonical_json_hash(snapshot_doc)
    _write_json(
        run_dir / "metadata.json",
        {
            "schema": "governance.work-run.snapshot.v2",
            "repo_fingerprint": "fp",
            "run_id": run_id,
            "archived_at": archived_at,
            "source_phase": source_phase,
            "source_active_gate": "Architecture Review Gate",
            "source_next": "5.3",
            "snapshot_digest": digest,
            "snapshot_digest_scope": "session_state",
            "archived_files": {"session_state": True, "plan_record": False},
        },
    )
    return snapshot_path, digest


def test_happy_build_audit_readout_uses_runs_and_pointer(tmp_path: Path) -> None:
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
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-2",
            "updated_at": "2026-03-05T20:34:32Z",
            "activation_reason": "new-work-session",
        },
    )

    snapshot_path, snapshot_digest = _write_run_archive(
        workspace,
        run_id="work-1",
        archived_at="2026-03-05T20:30:00Z",
        source_phase="6-PostFlight",
        state_phase="6-PostFlight",
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
                "snapshot_path": str(snapshot_path),
                "snapshot_digest": snapshot_digest,
                "phase": "4",
                "next": "5",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    assert isinstance(payload, dict)
    integrity = payload.get("integrity")
    assert isinstance(integrity, dict)
    active = payload.get("active")
    assert isinstance(active, dict)
    last_snapshot = payload.get("last_snapshot")
    assert isinstance(last_snapshot, dict)
    assert payload["contract_version"] == "AUDIT_READOUT_SPEC.v1"
    assert active["run_id"] == "work-2"
    assert last_snapshot["run_id"] == "work-1"
    assert last_snapshot["snapshot_digest"] == snapshot_digest
    assert integrity["snapshot_ref_present"] is True
    assert integrity["run_id_consistent"] is True
    assert integrity["active_run_pointer_consistent"] is True
    assert integrity["reactivation_chain_consistent"] is True


def test_edge_reactivation_keeps_last_snapshot_from_created_chain(tmp_path: Path) -> None:
    commands_home, _, workspace = _setup_workspace(tmp_path)
    _write_json(
        workspace / "SESSION_STATE.json",
        {
            "SESSION_STATE": {
                "session_run_id": "work-1",
                "Phase": "5-ArchitectureReview",
                "Next": "5.3",
                "active_gate": "Architecture Review Gate",
                "phase4_intake_updated_at": "2026-03-05T20:50:00Z",
            }
        },
    )
    _write_json(
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-1",
            "updated_at": "2026-03-05T20:50:00Z",
            "activation_reason": "reactivate-run",
        },
    )
    snapshot_path, snapshot_digest = _write_run_archive(
        workspace,
        run_id="work-3",
        archived_at="2026-03-05T20:45:00Z",
        source_phase="5-ArchitectureReview",
        state_phase="5-ArchitectureReview",
    )
    _write_run_archive(
        workspace,
        run_id="work-1",
        archived_at="2026-03-05T20:30:00Z",
        source_phase="5-ArchitectureReview",
        state_phase="5-ArchitectureReview",
    )

    (workspace / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "new_work_session_created",
                        "observed_at": "2026-03-05T20:46:00Z",
                        "repo_fingerprint": "fp",
                        "session_id": "sess-2",
                        "run_id": "work-3",
                        "new_run_id": "work-4",
                        "snapshot_path": str(snapshot_path),
                        "snapshot_digest": snapshot_digest,
                    }
                ),
                json.dumps(
                    {
                        "event": "work_session_reactivated",
                        "observed_at": "2026-03-05T20:50:00Z",
                        "repo_fingerprint": "fp",
                        "session_id": "sess-2",
                        "run_id": "work-1",
                        "previous_run_id": "work-4",
                        "reactivated_run_id": "work-1",
                        "snapshot_path": str(workspace / "runs" / "work-1" / "SESSION_STATE.json"),
                        "snapshot_digest": canonical_json_hash(
                            json.loads((workspace / "runs" / "work-1" / "SESSION_STATE.json").read_text(encoding="utf-8"))
                        ),
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    assert isinstance(payload, dict)
    active = payload.get("active")
    last_snapshot = payload.get("last_snapshot")
    integrity = payload.get("integrity")
    assert isinstance(active, dict)
    assert isinstance(last_snapshot, dict)
    assert isinstance(integrity, dict)
    assert active["run_id"] == "work-1"
    assert last_snapshot["run_id"] == "work-3"
    assert integrity["reactivation_chain_consistent"] is True


def test_bad_pointer_mismatch_sets_integrity_false(tmp_path: Path) -> None:
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
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-999",
            "updated_at": "2026-03-05T20:34:32Z",
            "activation_reason": "new-work-session",
        },
    )
    _write_run_archive(
        workspace,
        run_id="work-1",
        archived_at="2026-03-05T20:30:00Z",
        source_phase="6-PostFlight",
        state_phase="6-PostFlight",
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
                "snapshot_path": str(workspace / "runs" / "work-1" / "SESSION_STATE.json"),
                "snapshot_digest": canonical_json_hash(
                    json.loads((workspace / "runs" / "work-1" / "SESSION_STATE.json").read_text(encoding="utf-8"))
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    assert isinstance(payload, dict)
    integrity = payload.get("integrity")
    assert isinstance(integrity, dict)
    assert integrity["active_run_pointer_consistent"] is False
    notes = integrity.get("notes")
    assert isinstance(notes, list)
    assert "current-run-pointer-mismatch" in notes


def test_corner_reactivation_missing_run_reports_integrity_note(tmp_path: Path) -> None:
    commands_home, _, workspace = _setup_workspace(tmp_path)
    _write_json(
        workspace / "SESSION_STATE.json",
        {
            "SESSION_STATE": {
                "session_run_id": "work-5",
                "Phase": "5-ArchitectureReview",
                "Next": "5.3",
                "active_gate": "Architecture Review Gate",
                "phase4_intake_updated_at": "2026-03-05T21:00:00Z",
            }
        },
    )
    _write_json(
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-5",
            "updated_at": "2026-03-05T21:00:00Z",
            "activation_reason": "reactivate-run",
        },
    )
    _write_run_archive(
        workspace,
        run_id="work-4",
        archived_at="2026-03-05T20:59:00Z",
        source_phase="5-ArchitectureReview",
        state_phase="5-ArchitectureReview",
    )

    (workspace / "events.jsonl").write_text(
        json.dumps(
            {
                "event": "work_session_reactivated",
                "observed_at": "2026-03-05T21:00:00Z",
                "repo_fingerprint": "fp",
                "session_id": "sess-9",
                "run_id": "work-5",
                "previous_run_id": "work-6",
                "reactivated_run_id": "work-404",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    assert isinstance(payload, dict)
    integrity = payload.get("integrity")
    assert isinstance(integrity, dict)
    assert integrity["reactivation_chain_consistent"] is False
    notes = integrity.get("notes")
    assert isinstance(notes, list)
    assert any(note.startswith("reactivation-event-run-missing:") for note in notes)


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
    _write_json(
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-7",
            "updated_at": "2026-03-05T20:40:00Z",
            "activation_reason": "new-work-session",
        },
    )
    snapshot_path, digest = _write_run_archive(
        workspace,
        run_id="work-6",
        archived_at="2026-03-05T20:39:00Z",
        source_phase="5-ArchitectureReview",
        state_phase="5-ArchitectureReview",
    )
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


def test_archive_without_manifest_or_checksums_emits_notes(tmp_path: Path) -> None:
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
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-2",
            "updated_at": "2026-03-05T20:34:32Z",
            "activation_reason": "new-work-session",
        },
    )
    _write_run_archive(
        workspace,
        run_id="work-1",
        archived_at="2026-03-05T20:30:00Z",
        source_phase="6-PostFlight",
        state_phase="6-PostFlight",
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
                "snapshot_path": str(workspace / "runs" / "work-1" / "SESSION_STATE.json"),
                "snapshot_digest": canonical_json_hash(
                    json.loads((workspace / "runs" / "work-1" / "SESSION_STATE.json").read_text(encoding="utf-8"))
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    integrity = payload.get("integrity")
    assert isinstance(integrity, dict)
    notes = integrity.get("notes")
    assert isinstance(notes, list)
    assert "run-manifest-missing:work-1" in notes
    assert "run-checksums-missing:work-1" in notes


def test_last_snapshot_includes_run_and_integrity_status(tmp_path: Path) -> None:
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
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": "fp",
            "active_run_id": "work-2",
            "updated_at": "2026-03-05T20:34:32Z",
            "activation_reason": "new-work-session",
        },
    )
    _write_run_archive(
        workspace,
        run_id="work-1",
        archived_at="2026-03-05T20:30:00Z",
        source_phase="6-PostFlight",
        state_phase="6-PostFlight",
    )
    _write_json(
        workspace / "runs" / "work-1" / "run-manifest.json",
        {
            "schema": "governance.run-manifest.v1",
            "repo_fingerprint": "fp",
            "run_id": "work-1",
            "run_type": "analysis",
            "run_status": "finalized",
            "record_status": "finalized",
            "integrity_status": "passed",
            "finalized_at": "2026-03-05T20:30:00Z",
            "required_artifacts": {
                "session_state": True,
                "run_manifest": True,
                "metadata": True,
                "provenance": True,
                "plan_record": False,
                "pr_record": False,
                "checksums": True,
            },
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
                "snapshot_path": str(workspace / "runs" / "work-1" / "SESSION_STATE.json"),
                "snapshot_digest": canonical_json_hash(
                    json.loads((workspace / "runs" / "work-1" / "SESSION_STATE.json").read_text(encoding="utf-8"))
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_audit_readout(commands_home=commands_home)
    snapshot = payload.get("last_snapshot")
    assert isinstance(snapshot, dict)
    assert snapshot["run_status"] == "finalized"
    assert snapshot["integrity_status"] == "passed"
