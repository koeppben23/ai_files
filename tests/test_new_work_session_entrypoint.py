from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.entrypoints import new_work_session
from governance.domain.canonical_json import canonical_json_hash


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _setup_workspace(tmp_path: Path, *, phase: str = "5-ArchitectureReview") -> tuple[Path, Path, str]:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    fingerprint = "abc123def456abc123def456"
    session_path = workspaces_home / fingerprint / "SESSION_STATE.json"

    _write_json(
        commands_home / "governance.paths.json",
        {
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "configRoot": str(config_root),
                "commandsHome": str(commands_home),
                "workspacesHome": str(workspaces_home),
                "pythonCommand": "/usr/bin/python3",
            },
        },
    )
    _write_json(
        config_root / "SESSION_STATE.json",
        {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": fingerprint,
            "activeSessionStateFile": str(session_path),
        },
    )
    _write_json(
        session_path,
        {
            "SESSION_STATE": {
                "RepoFingerprint": fingerprint,
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "phase_transition_evidence": True,
                "Phase": phase,
                "phase": phase,
                "Next": "5.3",
                "Mode": "IN_PROGRESS",
                "OutputMode": "ARCHITECT",
                "DecisionSurface": {},
                "status": "OK",
                "active_gate": "Architecture Review Gate",
                "next_gate_condition": "Review in progress",
                "Bootstrap": {"Satisfied": True, "Present": True, "Evidence": "bootstrap-completed"},
                "ticket_intake_ready": True,
                "phase_ready": 4,
                "session_run_id": "run-old-001",
                "ActiveProfile": "profile.backend-python",
                "Ticket": "old ticket",
                "Task": "old task",
                "TicketRecordDigest": "ticket-old",
                "TaskRecordDigest": "task-old",
                "phase4_intake_source": "phase4-intake-bridge",
                "Gates": {
                    "P5-Architecture": "approved",
                    "P5.3-TestQuality": "pass",
                    "P5.4-BusinessRules": "compliant",
                    "P5.5-TechnicalDebt": "approved",
                    "P5.6-RollbackSafety": "approved",
                    "P6-ImplementationQA": "pending",
                },
                "Scope": {"BusinessRules": "extracted"},
                "BusinessRules": {
                    "Decision": "execute",
                    "Outcome": "extracted",
                    "ExecutionEvidence": True,
                    "InventoryFileStatus": "written",
                    "Rules": ["BR-7: must preserve old behavior"],
                    "Evidence": ["docs/rules.md:10"],
                    "Inventory": {"sha256": "abc123", "count": 1},
                },
                "ArchitectureDecisions": [{"Status": "approved"}],
            }
        },
    )
    return config_root, session_path, fingerprint


class TestNewWorkSessionEntrypoint:
    # -- Good --
    def test_creates_fresh_phase4_run_and_archives_previous(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-001", "--reason", "new ticket", "--quiet"])
        assert code == 0

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-created"

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"
        assert state["Next"] == "5"
        assert state["Ticket"] is None
        assert state["Task"] is None
        assert state["TicketRecordDigest"] is None
        assert state["TaskRecordDigest"] is None
        assert state["phase4_intake_evidence"] is False
        assert state["phase_transition_evidence"] is False
        assert state["Gates"]["P5-Architecture"] == "pending"
        assert state["ActiveProfile"] == "profile.backend-python"
        assert state["session_run_id"] != "run-old-001"
        assert state["Scope"]["BusinessRules"] == "unresolved"
        assert state["BusinessRules"]["Decision"] == "pending"
        assert state["BusinessRules"]["Outcome"] == "unresolved"
        assert state["BusinessRules"]["ExecutionEvidence"] is False
        assert state["BusinessRules"]["InventoryFileStatus"] != "written"
        assert "Rules" not in state["BusinessRules"]
        assert "Evidence" not in state["BusinessRules"]

        archived = sorted((session_path.parent / "work_runs").glob("*.json"))
        assert archived, "previous run snapshot must be archived"
        archived_payload = json.loads(archived[0].read_text(encoding="utf-8"))
        assert archived_payload["session_run_id"] == "run-old-001"
        assert archived_payload["source_active_gate"] == "Architecture Review Gate"
        assert archived_payload["source_next"] == "5.3"
        assert "ticket_digest" in archived_payload
        assert "task_digest" in archived_payload

        events = [json.loads(line) for line in (session_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        created = [e for e in events if e.get("event") == "new_work_session_created"][-1]
        assert created["snapshot_path"] == str(archived[0])
        assert created["snapshot_digest"] == canonical_json_hash(archived_payload)

    # -- Bad --
    def test_returns_blocked_when_pointer_is_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root = tmp_path / "config"
        commands_home = config_root / "commands"
        _write_json(
            commands_home / "governance.paths.json",
            {
                "schema": "opencode-governance.paths.v1",
                "paths": {
                    "configRoot": str(config_root),
                    "commandsHome": str(commands_home),
                    "workspacesHome": str(config_root / "workspaces"),
                    "pythonCommand": "/usr/bin/python3",
                },
            },
        )
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--quiet"])
        assert code == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"

    def test_writes_failure_marker_event_when_runtime_reset_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        session_path.write_text(json.dumps({}, ensure_ascii=True), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--quiet"])
        assert code == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-init-failed"

        events = [json.loads(line) for line in (session_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        failed = [e for e in events if e.get("event") == "new_work_session_init_failed"]
        assert failed, "failure marker event must be appended"
        assert failed[-1]["reason"] == "new-work-session-init-failed"

    # -- Edge --
    def test_dedupes_rapid_duplicate_trigger(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        first = new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-edge", "--quiet"])
        first_payload = json.loads(capsys.readouterr().out.strip())
        run_id = first_payload["run_id"]
        assert first == 0

        second = new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-edge", "--quiet"])
        second_payload = json.loads(capsys.readouterr().out.strip())
        assert second == 0
        assert second_payload["reason"] == "new-work-session-deduped"
        assert second_payload["run_id"] == run_id

        events = (session_path.parent / "events.jsonl").read_text(encoding="utf-8")
        assert "new_work_session_created" in events
        assert "new_work_session_deduped" in events
        parsed = [json.loads(line) for line in events.splitlines() if line.strip()]
        deduped = [e for e in parsed if e.get("event") == "new_work_session_deduped"][-1]
        assert deduped["reason"] == "recent-duplicate-trigger"

    def test_bypasses_dedupe_when_state_is_not_fresh_phase4_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        first = new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-stale", "--quiet"])
        first_payload = json.loads(capsys.readouterr().out.strip())
        first_run_id = first_payload["run_id"]
        assert first == 0

        doc = json.loads(session_path.read_text(encoding="utf-8"))
        state = doc["SESSION_STATE"]
        state["Phase"] = "5-ArchitectureReview"
        state["phase"] = "5-ArchitectureReview"
        state["Next"] = "5.3"
        state["active_gate"] = "Architecture Review Gate"
        session_path.write_text(json.dumps(doc, ensure_ascii=True), encoding="utf-8")

        second = new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-stale", "--quiet"])
        second_payload = json.loads(capsys.readouterr().out.strip())
        assert second == 0
        assert second_payload["reason"] == "new-work-session-created"
        assert second_payload["run_id"] != first_run_id

        events = (session_path.parent / "events.jsonl").read_text(encoding="utf-8")
        assert "new_work_session_dedupe_bypassed" in events
        assert events.count("new_work_session_created") >= 2

    # -- Corner --
    def test_initializes_when_legacy_run_id_is_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        doc = json.loads(session_path.read_text(encoding="utf-8"))
        doc["SESSION_STATE"].pop("session_run_id", None)
        session_path.write_text(json.dumps(doc, ensure_ascii=True), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--quiet"])
        assert code == 0
        _ = json.loads(capsys.readouterr().out.strip())

        archived = sorted((session_path.parent / "work_runs").glob("legacy-*.json"))
        assert archived, "legacy sessions without run id must still be archived"
