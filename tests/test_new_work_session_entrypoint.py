from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.entrypoints import new_work_session
from governance.domain.canonical_json import canonical_json_hash
from governance.infrastructure.workspace_paths import run_dir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _runs_root(session_path: Path) -> Path:
    return session_path.parent.parent / "governance-records" / session_path.parent.name / "runs"


def _run_archive_dir(session_path: Path, run_id: str) -> Path:
    return run_dir(session_path.parent.parent, session_path.parent.name, run_id)


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
    def test_creates_fresh_phase4_run_and_archives_previous(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-001", "--reason", "new ticket", "--quiet"])
        assert code == 0

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-created"

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"
        assert state["Next"] == "4"
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

        archived_dir = _run_archive_dir(session_path, "run-old-001")
        assert archived_dir.is_dir(), "previous run snapshot directory must be archived"
        archived_state = json.loads((archived_dir / "SESSION_STATE.json").read_text(encoding="utf-8"))
        archived_meta = json.loads((archived_dir / "metadata.json").read_text(encoding="utf-8"))
        assert archived_state["SESSION_STATE"]["session_run_id"] == "run-old-001"
        assert archived_meta["run_id"] == "run-old-001"
        assert archived_meta["source_active_gate"] == "Architecture Review Gate"
        assert archived_meta["source_next"] == "5.3"
        assert archived_meta["snapshot_digest_scope"] == "session_state"
        assert archived_meta["archived_files"]["session_state"] is True
        assert archived_meta["archived_files"]["plan_record"] is False
        assert "events.jsonl" not in {p.name for p in archived_dir.iterdir()}

        events = [json.loads(line) for line in (session_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        created = [e for e in events if e.get("event") == "new_work_session_created"][-1]
        assert created["snapshot_path"] == str(archived_dir / "SESSION_STATE.json")
        assert created["snapshot_digest"] == canonical_json_hash(archived_state)

    def test_rehydrates_business_rules_from_workspace_artifacts(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        workspace = session_path.parent
        (workspace / "business-rules-status.md").write_text(
            "Outcome: extracted\nExecutionEvidence: true\n",
            encoding="utf-8",
        )
        (workspace / "business-rules.md").write_text(
            "Rule: BR-900: audit entries are immutable\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-rehydrate", "--quiet"])
        assert code == 0
        _ = json.loads(capsys.readouterr().out.strip())

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Scope"]["BusinessRules"] == "extracted"
        assert state["BusinessRules"]["Outcome"] == "extracted"
        assert state["BusinessRules"]["ExecutionEvidence"] is True
        assert state["BusinessRules"]["InventoryLoaded"] is True
        assert state["BusinessRules"]["ExtractedCount"] == 1

    # -- Bad --
    def test_returns_blocked_when_pointer_is_missing(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root = short_tmp / "config"
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

    def test_writes_failure_marker_event_when_runtime_reset_fails(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
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
    def test_dedupes_rapid_duplicate_trigger(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
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

    def test_bypasses_dedupe_when_state_is_not_fresh_phase4_run(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
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

    def test_archives_plan_record_when_present(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, fingerprint = _setup_workspace(short_tmp)
        plan_record = {
            "schema": "governance.plan-record.v1",
            "status": "active",
            "versions": [{"version": 1, "content": "v1"}],
        }
        (session_path.parent / "plan-record.json").write_text(json.dumps(plan_record, ensure_ascii=True), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        _ = json.loads(capsys.readouterr().out.strip())

        archived_dir = _run_archive_dir(session_path, "run-old-001")
        archived_plan = archived_dir / "plan-record.json"
        assert archived_plan.is_file()
        assert json.loads(archived_plan.read_text(encoding="utf-8")) == plan_record
        archived_meta = json.loads((archived_dir / "metadata.json").read_text(encoding="utf-8"))
        assert archived_meta["archived_files"]["plan_record"] is True

    def test_does_not_emit_created_event_or_reset_when_archive_write_fails(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        before = json.loads(session_path.read_text(encoding="utf-8"))
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        real_writer = new_work_session._write_json_atomic

        def _boom(path: Path, payload: dict[str, object] | object) -> None:
            if str(path).replace("\\", "/").endswith("/run-old-001/SESSION_STATE.json"):
                raise RuntimeError("disk-full")
            real_writer(path, payload)  # type: ignore[arg-type]

        monkeypatch.setattr(new_work_session, "_write_json_atomic", _boom)

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-init-failed"

        after = json.loads(session_path.read_text(encoding="utf-8"))
        assert after == before
        events = [json.loads(line) for line in (session_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert not [e for e in events if e.get("event") == "new_work_session_created"]
        assert [e for e in events if e.get("event") == "new_work_session_init_failed"]

        failed_run = _run_archive_dir(session_path, "run-old-001")
        manifest = json.loads((failed_run / "run-manifest.json").read_text(encoding="utf-8"))
        metadata = json.loads((failed_run / "metadata.json").read_text(encoding="utf-8"))
        assert manifest["run_status"] == "failed"
        assert manifest["record_status"] == "invalidated"
        assert metadata["archive_status"] == "failed"

    # -- Corner --
    def test_initializes_when_legacy_run_id_is_missing(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        doc = json.loads(session_path.read_text(encoding="utf-8"))
        doc["SESSION_STATE"].pop("session_run_id", None)
        session_path.write_text(json.dumps(doc, ensure_ascii=True), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--quiet"])
        assert code == 0
        _ = json.loads(capsys.readouterr().out.strip())

        archived = sorted((_runs_root(session_path)).rglob("legacy-*"))
        assert archived, "legacy sessions without run id must still be archived"

    def test_archived_run_directories_are_immutable_across_multiple_runs(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        first = new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-a", "--quiet"])
        assert first == 0
        first_payload = json.loads(capsys.readouterr().out.strip())
        first_new_run = str(first_payload["run_id"])
        first_archived = _run_archive_dir(session_path, "run-old-001") / "SESSION_STATE.json"
        first_snapshot = json.loads(first_archived.read_text(encoding="utf-8"))

        state_doc = json.loads(session_path.read_text(encoding="utf-8"))
        state_doc["SESSION_STATE"]["Phase"] = "5-ArchitectureReview"
        state_doc["SESSION_STATE"]["phase"] = "5-ArchitectureReview"
        state_doc["SESSION_STATE"]["active_gate"] = "Architecture Review Gate"
        state_doc["SESSION_STATE"]["Next"] = "5.3"
        session_path.write_text(json.dumps(state_doc, ensure_ascii=True), encoding="utf-8")

        second = new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-a", "--quiet"])
        assert second == 0
        second_payload = json.loads(capsys.readouterr().out.strip())
        second_archived = _run_archive_dir(session_path, first_new_run) / "SESSION_STATE.json"
        assert second_archived.is_file()
        assert json.loads(first_archived.read_text(encoding="utf-8")) == first_snapshot
        assert str(second_payload["run_id"]) != first_new_run

    def test_retry_reuses_failed_archive_slot_after_partial_failure(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        real_writer = new_work_session._write_json_atomic

        def _boom_once(path: Path, payload: dict[str, object] | object) -> None:
            if str(path).replace("\\", "/").endswith("/run-old-001/SESSION_STATE.json"):
                raise RuntimeError("disk-full")
            real_writer(path, payload)  # type: ignore[arg-type]

        monkeypatch.setattr(new_work_session, "_write_json_atomic", _boom_once)
        first_code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert first_code == 2
        _ = json.loads(capsys.readouterr().out.strip())

        failed_manifest = json.loads((_run_archive_dir(session_path, "run-old-001") / "run-manifest.json").read_text(encoding="utf-8"))
        assert failed_manifest["run_status"] == "failed"

        monkeypatch.setattr(new_work_session, "_write_json_atomic", real_writer)
        second_code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert second_code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-created"

        repaired_archive = _run_archive_dir(session_path, "run-old-001") / "SESSION_STATE.json"
        assert repaired_archive.is_file()

    def test_runtime_purge_removes_stale_runtime_files_only(self, short_tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(short_tmp)
        workspace = session_path.parent
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        (workspace / "repo-cache.yaml").write_text("old", encoding="utf-8")
        (workspace / "workspace-memory.yaml").write_text("old", encoding="utf-8")
        (workspace / "decision-pack.md").write_text("old", encoding="utf-8")
        (workspace / "notes.tmp").write_text("keep", encoding="utf-8")

        code = new_work_session.main(["--trigger-source", "cli", "--quiet"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "new-work-session-created"

        assert not (workspace / "repo-cache.yaml").exists()
        assert not (workspace / "workspace-memory.yaml").exists()
        assert not (workspace / "decision-pack.md").exists()
        assert (workspace / "notes.tmp").exists()
        assert (run_dir(workspace.parent, workspace.name, "run-old-001") / "run-manifest.json").is_file()
