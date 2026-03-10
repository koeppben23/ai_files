from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from governance.entrypoints import work_session_restore
from governance.domain.canonical_json import canonical_json_hash


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_archive_run(workspace: Path, run_id: str, phase: str, next_token: str, gate: str) -> None:
    run_root = workspace / "runs" / run_id
    session_state_doc = {
        "SESSION_STATE": {
            "RepoFingerprint": "abc123def456abc123def456",
            "session_run_id": run_id,
            "Phase": phase,
            "phase": phase,
            "Next": next_token,
            "active_gate": gate,
        }
    }
    _write_json(run_root / "SESSION_STATE.json", session_state_doc)
    _write_json(
        run_root / "metadata.json",
        {
            "schema": "governance.work-run.snapshot.v2",
            "repo_fingerprint": "abc123def456abc123def456",
            "run_id": run_id,
            "archived_at": "2026-01-01T00:00:00Z",
            "snapshot_digest": canonical_json_hash(session_state_doc),
            "snapshot_digest_scope": "session_state",
            "archive_status": "materialized",
            "archived_files": {
                "session_state": True,
                "plan_record": False,
                "pr_record": False,
                "run_manifest": True,
                "provenance_record": True,
                "checksums": True,
            },
        },
    )
    _write_json(
        run_root / "run-manifest.json",
        {
            "schema": "governance.run-manifest.v1",
            "repo_fingerprint": "abc123def456abc123def456",
            "run_id": run_id,
            "run_type": "analysis",
            "materialized_at": "2026-01-01T00:00:00Z",
            "run_status": "materialized",
            "record_status": "draft",
            "finalized_at": None,
            "integrity_status": "pending",
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
    _write_json(
        run_root / "provenance-record.json",
        {
            "schema": "governance.provenance-record.v1",
            "repo_fingerprint": "abc123def456abc123def456",
            "run_id": run_id,
            "trigger": "new_work_session_created",
            "binding": {
                "repo_fingerprint": "abc123def456abc123def456",
                "session_run_id": run_id,
            },
            "launcher": "governance.entrypoints.new_work_session",
            "timestamps": {"materialized_at": "2026-01-01T00:00:00Z"},
        },
    )

    checksums = {
        "schema": "governance.run-checksums.v1",
        "files": {
            "SESSION_STATE.json": _sha256_file(run_root / "SESSION_STATE.json"),
            "metadata.json": _sha256_file(run_root / "metadata.json"),
            "run-manifest.json": _sha256_file(run_root / "run-manifest.json"),
            "provenance-record.json": _sha256_file(run_root / "provenance-record.json"),
        },
    }
    _write_json(run_root / "checksums.json", checksums)


def _setup_workspace(tmp_path: Path) -> tuple[Path, Path, str]:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    fingerprint = "abc123def456abc123def456"
    workspace = workspaces_home / fingerprint
    session_path = workspace / "SESSION_STATE.json"

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
                "session_run_id": "work-2",
                "Phase": "4",
                "phase": "4",
                "Next": "5",
                "active_gate": "Ticket Input Gate",
            }
        },
    )
    _write_json(
        workspace / "current_run.json",
        {
            "schema": "governance.current-run-pointer.v1",
            "repo_fingerprint": fingerprint,
            "active_run_id": "work-2",
            "updated_at": "2026-01-01T00:00:00Z",
            "activation_reason": "new-work-session",
        },
    )
    _write_archive_run(workspace, "work-1", "5-ArchitectureReview", "5.3", "Architecture Review Gate")
    _write_archive_run(workspace, "work-2", "4", "5", "Ticket Input Gate")
    (workspace / "plan-record.json").write_text(
        json.dumps({"schema": "governance.plan-record.v1", "status": "active", "versions": [{"version": 1}]}, ensure_ascii=True),
        encoding="utf-8",
    )
    return config_root, workspace, fingerprint


class TestWorkSessionRestoreEntrypoint:
    def test_revisit_mode_is_read_only_and_emits_no_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_root, workspace, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        before = (workspace / "events.jsonl").read_text(encoding="utf-8") if (workspace / "events.jsonl").exists() else ""

        code = work_session_restore.main(["--mode", "revisit", "--run-id", "work-1", "--quiet"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "work-session-revisit"
        assert payload["run_id"] == "work-1"
        assert payload["phase"] == "5-ArchitectureReview"

        after = (workspace / "events.jsonl").read_text(encoding="utf-8") if (workspace / "events.jsonl").exists() else ""
        assert after == before

    def test_reactivate_restores_root_updates_pointer_and_writes_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_root, workspace, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = work_session_restore.main(["--mode", "reactivate", "--run-id", "work-1", "--session-id", "sess-r1", "--quiet"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "work-session-reactivated"

        active_state = json.loads((workspace / "SESSION_STATE.json").read_text(encoding="utf-8"))
        archived_state = json.loads((workspace / "runs" / "work-1" / "SESSION_STATE.json").read_text(encoding="utf-8"))
        assert active_state == archived_state

        pointer = json.loads((workspace / "current_run.json").read_text(encoding="utf-8"))
        assert pointer["active_run_id"] == "work-1"
        assert pointer["activation_reason"] == "reactivate-run"

        events = [json.loads(line) for line in (workspace / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        reactivated = [e for e in events if e.get("event") == "work_session_reactivated"]
        assert reactivated
        assert reactivated[-1]["previous_run_id"] == "work-2"
        assert reactivated[-1]["reactivated_run_id"] == "work-1"

    def test_reactivate_deletes_root_plan_record_when_target_has_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_root, workspace, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        assert (workspace / "plan-record.json").exists()

        code = work_session_restore.main(["--mode", "reactivate", "--run-id", "work-1", "--quiet"])
        assert code == 0
        _ = json.loads(capsys.readouterr().out.strip())

        assert not (workspace / "plan-record.json").exists()

    def test_reactivate_same_run_is_noop_and_writes_no_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_root, workspace, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = work_session_restore.main(["--mode", "reactivate", "--run-id", "work-2", "--quiet"])
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "work-session-reactivate-noop"
        assert not (workspace / "events.jsonl").exists()

    def test_missing_run_blocks_without_mutation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config_root, workspace, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        before_state = (workspace / "SESSION_STATE.json").read_text(encoding="utf-8")
        before_pointer = (workspace / "current_run.json").read_text(encoding="utf-8")

        code = work_session_restore.main(["--mode", "reactivate", "--run-id", "work-404", "--quiet"])
        assert code == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "run-archive-unavailable"

        assert (workspace / "SESSION_STATE.json").read_text(encoding="utf-8") == before_state
        assert (workspace / "current_run.json").read_text(encoding="utf-8") == before_pointer
        assert not (workspace / "events.jsonl").exists()

    def test_tampered_archive_blocks_reactivation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, workspace, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        before_state = (workspace / "SESSION_STATE.json").read_text(encoding="utf-8")
        before_pointer = (workspace / "current_run.json").read_text(encoding="utf-8")

        (workspace / "runs" / "work-1" / "SESSION_STATE.json").write_text('{"tampered":true}', encoding="utf-8")

        code = work_session_restore.main(["--mode", "reactivate", "--run-id", "work-1", "--quiet"])
        assert code == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "run-archive-integrity-failed"

        assert (workspace / "SESSION_STATE.json").read_text(encoding="utf-8") == before_state
        assert (workspace / "current_run.json").read_text(encoding="utf-8") == before_pointer
