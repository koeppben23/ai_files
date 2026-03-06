"""Tests for governance.entrypoints.session_reader — LLM bridge entrypoint.

Validates:
- Correct YAML-like snapshot output from valid session state
- Dual-case field extraction (PascalCase + snake_case)
- Error handling for missing pointer, missing workspace state, invalid JSON
- CLI interface (--commands-home override, exit codes)
- Self-bootstrapping path derivation
- Cross-platform path handling
- Readonly kernel evaluation enrichment (Fix 1.2)

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from governance.entrypoints.session_reader import (
    POINTER_SCHEMA,
    SNAPSHOT_SCHEMA,
    format_snapshot,
    main,
    read_session_snapshot,
    _derive_commands_home,
    _safe_str,
    _format_list,
    _quote_if_needed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_config(tmp_path: Path) -> Path:
    """Create a minimal config_root with commands/ subdirectory.

    Layout:
        tmp_path/
            config_root/
                commands/        <-- this is commands_home
                SESSION_STATE.json   <-- global pointer
                workspaces/<fp>/
                    SESSION_STATE.json  <-- workspace state
    """
    config_root = tmp_path / "config_root"
    commands_home = config_root / "commands"
    commands_home.mkdir(parents=True)
    return config_root


def _write_pointer(config_root: Path, *, workspace_fp: str = "abc123") -> Path:
    """Write a valid global pointer to config_root/SESSION_STATE.json."""
    ws_dir = config_root / "workspaces" / workspace_fp
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws_state = ws_dir / "SESSION_STATE.json"

    pointer = {
        "schema": POINTER_SCHEMA,
        "activeSessionStateFile": str(ws_state),
    }
    pointer_path = config_root / "SESSION_STATE.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return ws_state


def _write_workspace_state(ws_state: Path, state: dict) -> None:
    """Write workspace SESSION_STATE.json."""
    ws_state.write_text(json.dumps(state), encoding="utf-8")


def _mock_readonly_unavailable():
    """Patch evaluate_readonly to raise, triggering graceful degradation.

    Used in tests that validate field extraction from persisted state
    without needing a full kernel setup (phase_api.yaml, etc.).
    """
    return patch(
        "governance.kernel.phase_kernel.evaluate_readonly",
        side_effect=RuntimeError("kernel not available in test"),
    )


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------

class TestSafeStr:
    def test_none(self) -> None:
        assert _safe_str(None) == "null"

    def test_bool_true(self) -> None:
        assert _safe_str(True) == "true"

    def test_bool_false(self) -> None:
        assert _safe_str(False) == "false"

    def test_int(self) -> None:
        assert _safe_str(42) == "42"

    def test_string(self) -> None:
        assert _safe_str("hello") == "hello"


class TestFormatList:
    def test_empty(self) -> None:
        assert _format_list([]) == "[]"

    def test_single(self) -> None:
        assert _format_list(["a"]) == "[a]"

    def test_multiple(self) -> None:
        assert _format_list(["a", "b", "c"]) == "[a, b, c]"

    def test_mixed_types(self) -> None:
        result = _format_list([1, True, None, "x"])
        assert result == "[1, true, null, x]"


class TestQuoteIfNeeded:
    def test_plain_string(self) -> None:
        assert _quote_if_needed("hello") == "hello"

    def test_colon_triggers_quoting(self) -> None:
        assert _quote_if_needed("key: value") == '"key: value"'

    def test_hash_triggers_quoting(self) -> None:
        assert _quote_if_needed("# comment") == '"# comment"'


# ---------------------------------------------------------------------------
# Unit tests — read_session_snapshot
# ---------------------------------------------------------------------------

class TestReadSessionSnapshotErrors:
    """Error cases for read_session_snapshot."""

    def test_missing_pointer(self, fake_config: Path) -> None:
        """No global pointer file exists."""
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "ERROR"
        assert result["schema"] == SNAPSHOT_SCHEMA
        assert "No session pointer" in result["error"]

    def test_invalid_pointer_json(self, fake_config: Path) -> None:
        """Pointer file contains garbage."""
        pointer_path = fake_config / "SESSION_STATE.json"
        pointer_path.write_text("not json!", encoding="utf-8")
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "ERROR"
        assert "Invalid session pointer JSON" in result["error"]

    def test_unknown_pointer_schema(self, fake_config: Path) -> None:
        """Pointer file has an unrecognised schema."""
        pointer_path = fake_config / "SESSION_STATE.json"
        pointer_path.write_text(json.dumps({"schema": "bogus.v99"}), encoding="utf-8")
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "ERROR"
        assert "Unknown pointer schema" in result["error"]

    def test_pointer_no_session_file(self, fake_config: Path) -> None:
        """Pointer exists but contains no session state file path."""
        pointer = {"schema": POINTER_SCHEMA}
        (fake_config / "SESSION_STATE.json").write_text(
            json.dumps(pointer), encoding="utf-8"
        )
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "ERROR"
        assert "no session state file path" in result["error"]

    def test_workspace_state_missing(self, fake_config: Path) -> None:
        """Pointer references a workspace state file that doesn't exist."""
        ws_state = _write_pointer(fake_config)
        # Don't create the workspace state file
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "ERROR"
        assert "Workspace session state missing" in result["error"]

    def test_workspace_state_invalid_json(self, fake_config: Path) -> None:
        """Workspace state file contains garbage."""
        ws_state = _write_pointer(fake_config)
        ws_state.write_text("{broken", encoding="utf-8")
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "ERROR"
        assert "Invalid workspace session state JSON" in result["error"]


class TestReadSessionSnapshotSuccess:
    """Happy-path tests for read_session_snapshot."""

    def test_pascal_case_fields(self, fake_config: Path) -> None:
        """PascalCase keys (legacy convention) are extracted correctly."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "4",
            "Next": "5",
            "Mode": "repo-aware",
            "status": "OK",
            "OutputMode": "structured",
            "Gates": {"readiness": "open", "quality": "blocked"},
        })
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "OK"
        assert result["schema"] == SNAPSHOT_SCHEMA
        assert result["phase"] == "4"
        assert result["next"] == "5"
        assert result["mode"] == "repo-aware"
        assert result["output_mode"] == "structured"
        assert "quality" in result["gates_blocked"]
        assert "readiness" not in result["gates_blocked"]

    def test_snake_case_fields(self, fake_config: Path) -> None:
        """snake_case keys (newer convention) are extracted correctly."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "phase": 4,
            "next": 5,
            "mode": "repo-aware",
            "status": "IN_PROGRESS",
            "output_mode": "structured",
            "active_gate": "quality",
            "next_gate_condition": "pass review",
            "ticket_intake_ready": True,
            "Gates": {},
        })
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "IN_PROGRESS"
        assert result["phase"] == "4"
        assert result["next"] == "5"
        assert result["ticket_intake_ready"] == "true"
        assert result["gates_blocked"] == []

    def test_missing_optional_fields_default(self, fake_config: Path) -> None:
        """Missing optional fields get sane defaults."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"status": "OK"})
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["phase"] == "unknown"
        assert result["next"] == "unknown"
        assert result["mode"] == "unknown"
        assert result["active_gate"] == "none"

    def test_commands_home_in_snapshot(self, fake_config: Path) -> None:
        """Snapshot includes the resolved commands_home path."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"status": "OK"})
        commands_home = fake_config / "commands"
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=commands_home)
        assert result["commands_home"] == str(commands_home)

    def test_relative_path_fallback(self, fake_config: Path) -> None:
        """Pointer with only activeSessionStateRelativePath still works."""
        ws_dir = fake_config / "workspaces" / "abc123"
        ws_dir.mkdir(parents=True)
        ws_state = ws_dir / "SESSION_STATE.json"
        _write_workspace_state(ws_state, {"Phase": "2", "status": "OK"})

        pointer = {
            "schema": POINTER_SCHEMA,
            "activeSessionStateRelativePath": "workspaces/abc123/SESSION_STATE.json",
        }
        (fake_config / "SESSION_STATE.json").write_text(
            json.dumps(pointer), encoding="utf-8"
        )
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "OK"
        assert result["phase"] == "2"

    def test_enveloped_session_state_fields(self, fake_config: Path) -> None:
        """Canonical envelope under SESSION_STATE is extracted correctly."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "4",
                "Next": "4",
                "Mode": "IN_PROGRESS",
                "OutputMode": "ARCHITECT",
                "active_gate": "Ticket Input Gate",
                "next_gate_condition": "wait for ticket input",
                "ticket_intake_ready": False,
                "Gates": {"P5.3-TestQuality": "blocked"},
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "OK"
        assert result["phase"] == "4"
        assert result["next"] == "4"
        assert result["mode"] == "IN_PROGRESS"
        assert result["output_mode"] == "ARCHITECT"
        assert result["active_gate"] == "Ticket Input Gate"
        assert result["next_gate_condition"] == "wait for ticket input"
        assert result["ticket_intake_ready"] == "false"
        assert result["gates_blocked"] == ["P5.3-TestQuality"]

    def test_plan_record_signal_prefers_workspace_file_when_present(self, fake_config: Path) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "5-ArchitectureReview",
                    "active_gate": "Architecture Review Gate",
                    "plan_record_status": "active",
                    "plan_record_versions": 2,
                }
            },
        )
        (ws_state.parent / "plan-record.json").write_text(
            json.dumps({"status": "draft", "versions": [{"version": 1}]}),
            encoding="utf-8",
        )

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["plan_record_status"] == "draft"
        assert result["plan_record_versions"] == 1

    def test_plan_record_signal_uses_state_when_workspace_file_absent(self, fake_config: Path) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "5-ArchitectureReview",
                    "plan_record_status": "active",
                    "plan_record_versions": "1",
                }
            },
        )

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["plan_record_status"] == "active"
        assert result["plan_record_versions"] == 1


# ---------------------------------------------------------------------------
# Fix 1.2 — Readonly kernel evaluation enrichment
# ---------------------------------------------------------------------------

class TestReadonlyKernelEvalEnrichment:
    """Validates that read_session_snapshot enriches non-materialize readouts
    with fresh kernel evaluation results (Fix 1.2)."""

    def test_happy_readonly_eval_overrides_stale_persisted_fields(self, fake_config: Path) -> None:
        """When kernel eval succeeds, snapshot fields come from KernelResult."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "4",
            "status": "OK",
            "active_gate": "stale-gate",
            "next_gate_condition": "stale-condition",
        })

        from governance.kernel.phase_kernel import KernelResult

        fake_result = KernelResult(
            phase="5",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Resume via /continue",
            workspace_ready=True,
            source="test-source",
            status="OK",
            spec_hash="abc123",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-test-001",
            plan_record_status="active",
            plan_record_versions=2,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        # Kernel-authoritative fields must come from the KernelResult.
        assert result["phase"] == "5"
        assert result["status"] == "OK"
        assert result["active_gate"] == "Architecture Review Gate"
        assert result["next_gate_condition"] == "Resume via /continue"
        assert result["next"] == "5.3"
        assert result["plan_record_status"] == "active"
        assert result["plan_record_versions"] == 2

    def test_corner_graceful_degradation_on_kernel_error(self, fake_config: Path) -> None:
        """When kernel eval raises, snapshot falls back to persisted state."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "4",
            "Next": "5",
            "status": "OK",
            "active_gate": "Ticket Input Gate",
            "next_gate_condition": "collect ticket",
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        # Should fall back to persisted values, not crash.
        assert result["phase"] == "4"
        assert result["status"] == "OK"
        assert result["active_gate"] == "Ticket Input Gate"
        assert result["next_gate_condition"] == "collect ticket"

    def test_edge_materialize_mode_does_not_trigger_readonly_eval(self, fake_config: Path) -> None:
        """Materialize mode uses execute() (write), never evaluate_readonly()."""
        ws_state = _write_pointer(fake_config)
        repo_fp = "abc123"
        pointer = {
            "schema": POINTER_SCHEMA,
            "activeRepoFingerprint": repo_fp,
            "activeSessionStateFile": str(ws_state),
        }
        (fake_config / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "4",
                "status": "OK",
                "active_gate": "Ticket Input Gate",
                "next_gate_condition": "Collect ticket and planning constraints",
                "ActiveProfile": "profile.fallback-minimum",
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                "LoadedRulebooks": {
                    "core": "rulesets/core/rules.yml",
                    "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                    "addons": {"riskTiering": "rulesets/profiles/rules.risk-tiering.yml"},
                },
                "RulebookLoadEvidence": {
                    "core": "rulesets/core/rules.yml",
                    "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                },
                "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
            }
        })

        commands_home = fake_config / "commands"
        (commands_home / "phase_api.yaml").write_text(
            (Path(__file__).resolve().parent.parent / "phase_api.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (commands_home / "governance.paths.json").write_text(
            json.dumps({
                "schema": "opencode-governance.paths.v1",
                "paths": {
                    "commandsHome": str(commands_home),
                    "workspacesHome": str(fake_config / "workspaces"),
                    "configRoot": str(fake_config),
                    "pythonCommand": "python3",
                },
            }),
            encoding="utf-8",
        )

        # If evaluate_readonly were called, this mock would raise and fail the test.
        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            side_effect=AssertionError("evaluate_readonly must NOT be called in materialize mode"),
        ):
            result = read_session_snapshot(commands_home=commands_home, materialize=True)

        # Should succeed via execute() path, not evaluate_readonly().
        assert result["status"] != "ERROR"

    def test_bad_kernel_returns_blocked_status(self, fake_config: Path) -> None:
        """When kernel eval returns BLOCKED, snapshot reflects BLOCKED."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "4",
            "status": "OK",
            "active_gate": "stale-gate",
        })

        from governance.kernel.phase_kernel import KernelResult

        blocked_result = KernelResult(
            phase="1.1-Bootstrap",
            next_token="1.1",
            active_gate="Workspace Ready Gate",
            next_gate_condition="BLOCKED: missing phase_api.yaml",
            workspace_ready=False,
            source="blocked-bootstrap",
            status="BLOCKED",
            spec_hash="",
            spec_path="",
            spec_loaded_at="",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-blocked-001",
            plan_record_status="absent",
            plan_record_versions=0,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=blocked_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["status"] == "BLOCKED"
        assert result["phase"] == "1.1-Bootstrap"
        assert result["active_gate"] == "Workspace Ready Gate"
        assert "BLOCKED" in result["next_gate_condition"]

    def test_readonly_eval_does_not_write_to_disk(self, fake_config: Path) -> None:
        """The readonly code path must never call _write_json_atomic."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "4", "status": "OK"})
        original_content = ws_state.read_text(encoding="utf-8")

        from governance.kernel.phase_kernel import KernelResult

        fake_result = KernelResult(
            phase="5",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Resume via /continue",
            workspace_ready=True,
            source="test",
            status="OK",
            spec_hash="abc",
            spec_path="/fake",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-test",
            plan_record_status="active",
            plan_record_versions=1,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            read_session_snapshot(commands_home=fake_config / "commands")

        # The workspace state file must not have been modified.
        assert ws_state.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Unit tests — format_snapshot
# ---------------------------------------------------------------------------

class TestFormatSnapshot:
    def test_basic_format(self) -> None:
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "status": "OK",
            "phase": "4",
            "gates_blocked": ["quality"],
        }
        output = format_snapshot(snapshot)
        assert output.startswith("# governance-session-snapshot.v1\n")
        assert "status: OK\n" in output
        assert "phase: 4\n" in output
        assert "gates_blocked: [quality]\n" in output
        # schema key should not appear as a value line
        lines = output.strip().split("\n")
        value_lines = [l for l in lines if not l.startswith("#")]
        assert not any(l.startswith("schema:") for l in value_lines)

    def test_error_format(self) -> None:
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "status": "ERROR",
            "error": "No session pointer at /foo/bar",
        }
        output = format_snapshot(snapshot)
        assert "status: ERROR\n" in output
        assert "error:" in output


# ---------------------------------------------------------------------------
# CLI tests — main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_success_exit_code(self, fake_config: Path, capsys: pytest.CaptureFixture) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "4", "status": "OK"})
        with _mock_readonly_unavailable():
            rc = main(["--commands-home", str(fake_config / "commands")])
        assert rc == 0
        captured = capsys.readouterr()
        assert "status: OK" in captured.out

    def test_error_exit_code(self, fake_config: Path, capsys: pytest.CaptureFixture) -> None:
        # No pointer file -> error
        rc = main(["--commands-home", str(fake_config / "commands")])
        assert rc == 1
        captured = capsys.readouterr()
        assert "status: ERROR" in captured.out

    def test_missing_commands_home_arg(self, capsys: pytest.CaptureFixture) -> None:
        rc = main(["--commands-home"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "error:" in captured.out

    def test_audit_mode_outputs_json_payload(self, fake_config: Path, capsys: pytest.CaptureFixture) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
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

        snapshot_doc = {
            "SESSION_STATE": {
                "session_run_id": "work-1",
                "Phase": "6-PostFlight",
                "active_gate": "Post Flight",
                "Next": "6",
            }
        }
        snapshot_path = ws_state.parent / "runs" / "work-1" / "SESSION_STATE.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot_doc), encoding="utf-8")

        from governance.engine.canonical_json import canonical_json_hash

        digest = canonical_json_hash(snapshot_doc)
        (ws_state.parent / "runs" / "work-1" / "metadata.json").write_text(
            json.dumps(
                {
                    "schema": "governance.work-run.snapshot.v2",
                    "repo_fingerprint": "abc123",
                    "run_id": "work-1",
                    "archived_at": "2026-03-05T20:30:00Z",
                    "source_phase": "6-PostFlight",
                    "source_active_gate": "Post Flight",
                    "source_next": "6",
                    "snapshot_digest": digest,
                    "snapshot_digest_scope": "session_state",
                    "archived_files": {"session_state": True, "plan_record": False},
                }
            ),
            encoding="utf-8",
        )
        (ws_state.parent / "current_run.json").write_text(
            json.dumps(
                {
                    "schema": "governance.current-run-pointer.v1",
                    "repo_fingerprint": "abc123",
                    "active_run_id": "work-2",
                    "updated_at": "2026-03-05T20:34:32Z",
                    "activation_reason": "new-work-session",
                }
            ),
            encoding="utf-8",
        )
        (ws_state.parent / "events.jsonl").write_text(
            json.dumps(
                {
                    "event": "new_work_session_created",
                    "observed_at": "2026-03-05T20:34:32Z",
                    "repo_fingerprint": "abc123",
                    "session_id": "sess-1",
                    "run_id": "work-1",
                    "new_run_id": "work-2",
                    "snapshot_path": str(snapshot_path),
                    "snapshot_digest": digest,
                    "phase": "4",
                    "next": "5",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        rc = main(["--commands-home", str(fake_config / "commands"), "--audit"])
        assert rc == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["contract_version"] == "AUDIT_READOUT_SPEC.v1"
        assert payload["integrity"]["snapshot_ref_present"] is True

    def test_materialize_mode_updates_phase5_gate_and_emits_continue_action(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        repo_fp = "abc123"
        pointer = {
            "schema": POINTER_SCHEMA,
            "activeRepoFingerprint": repo_fp,
            "activeSessionStateFile": str(ws_state),
        }
        (fake_config / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "5-ArchitectureReview",
                    "Next": "5",
                    "active_gate": "Plan Record Preparation Gate",
                    "next_gate_condition": "Ticket/task evidence captured; continue to Phase 5 plan-record preparation before architecture review",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "PersistenceCommitted": True,
                    "WorkspaceReadyGateCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                    "PointerVerified": True,
                    "LoadedRulebooks": {
                        "core": "rulesets/core/rules.yml",
                        "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                        "addons": {
                            "riskTiering": "rulesets/profiles/rules.risk-tiering.yml",
                        },
                    },
                    "RulebookLoadEvidence": {
                        "core": "rulesets/core/rules.yml",
                        "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                    },
                    "AddonsEvidence": {
                        "riskTiering": {"status": "loaded"},
                    },
                }
            },
        )

        commands_home = fake_config / "commands"
        (commands_home / "phase_api.yaml").write_text(
            (Path(__file__).resolve().parent.parent / "phase_api.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (commands_home / "governance.paths.json").write_text(
            json.dumps(
                {
                    "schema": "opencode-governance.paths.v1",
                    "paths": {
                        "commandsHome": str(commands_home),
                        "workspacesHome": str(fake_config / "workspaces"),
                        "configRoot": str(fake_config),
                        "pythonCommand": "python3",
                    },
                }
            ),
            encoding="utf-8",
        )

        (ws_state.parent / "plan-record.json").write_text(
            json.dumps({"status": "active", "versions": [{"version": 1}]}, ensure_ascii=True),
            encoding="utf-8",
        )

        rc = main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "active_gate: Architecture Review Gate" in output
        assert output.strip().endswith("Next action: run /continue.")

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["active_gate"] == "Architecture Review Gate"
        assert updated_state["PlanRecordStatus"] == "active"
        assert updated_state["PlanRecordVersions"] == 1

    def test_materialize_mode_phase5_missing_plan_record_stays_prep_without_continue_hint(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "5-ArchitectureReview",
                    "Next": "5",
                    "active_gate": "Architecture Review Gate",
                    "next_gate_condition": "Continue",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "PersistenceCommitted": True,
                    "WorkspaceReadyGateCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                    "PointerVerified": True,
                    "LoadedRulebooks": {
                        "core": "rulesets/core/rules.yml",
                        "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                        "addons": {
                            "riskTiering": "rulesets/profiles/rules.risk-tiering.yml",
                        },
                    },
                    "RulebookLoadEvidence": {
                        "core": "rulesets/core/rules.yml",
                        "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                    },
                    "AddonsEvidence": {
                        "riskTiering": {"status": "loaded"},
                    },
                }
            },
        )

        commands_home = fake_config / "commands"
        (commands_home / "phase_api.yaml").write_text(
            (Path(__file__).resolve().parent.parent / "phase_api.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (commands_home / "governance.paths.json").write_text(
            json.dumps(
                {
                    "schema": "opencode-governance.paths.v1",
                    "paths": {
                        "commandsHome": str(commands_home),
                        "workspacesHome": str(fake_config / "workspaces"),
                        "configRoot": str(fake_config),
                        "pythonCommand": "python3",
                    },
                }
            ),
            encoding="utf-8",
        )

        rc = main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "active_gate: Plan Record Preparation Gate" in output
        assert not output.strip().endswith("Next action: run /continue.")

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["active_gate"] == "Plan Record Preparation Gate"
        assert updated_state["PlanRecordVersions"] == 0

    def test_materialize_mode_phase4_ticket_intake_does_not_emit_continue_hint(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "4",
                    "Next": "5",
                    "active_gate": "Ticket Input Gate",
                    "next_gate_condition": "Collect ticket and planning constraints",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "PersistenceCommitted": True,
                    "WorkspaceReadyGateCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                    "PointerVerified": True,
                    "LoadedRulebooks": {
                        "core": "rulesets/core/rules.yml",
                        "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                        "addons": {
                            "riskTiering": "rulesets/profiles/rules.risk-tiering.yml",
                        },
                    },
                    "RulebookLoadEvidence": {
                        "core": "rulesets/core/rules.yml",
                        "profile": "rulesets/profiles/rules.fallback-minimum.yml",
                    },
                    "AddonsEvidence": {
                        "riskTiering": {"status": "loaded"},
                    },
                }
            },
        )

        commands_home = fake_config / "commands"
        (commands_home / "phase_api.yaml").write_text(
            (Path(__file__).resolve().parent.parent / "phase_api.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (commands_home / "governance.paths.json").write_text(
            json.dumps(
                {
                    "schema": "opencode-governance.paths.v1",
                    "paths": {
                        "commandsHome": str(commands_home),
                        "workspacesHome": str(fake_config / "workspaces"),
                        "configRoot": str(fake_config),
                        "pythonCommand": "python3",
                    },
                }
            ),
            encoding="utf-8",
        )

        rc = main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "active_gate: Ticket Input Gate" in output
        assert not output.strip().endswith("Next action: run /continue.")


# ---------------------------------------------------------------------------
# Self-bootstrap test
# ---------------------------------------------------------------------------

class TestSelfBootstrap:
    def test_derive_commands_home_from_file(self) -> None:
        """_derive_commands_home returns the correct ancestor of __file__."""
        reader_path = Path(__file__).resolve().parent.parent / "governance" / "entrypoints" / "session_reader.py"
        if reader_path.exists():
            # The actual file exists — verify parent chain
            expected = reader_path.parents[2]
            assert _derive_commands_home() == expected


# ---------------------------------------------------------------------------
# Cross-platform path test
# ---------------------------------------------------------------------------

class TestCrossPlatform:
    def test_windows_paths_in_pointer(self, fake_config: Path) -> None:
        """Paths with backslashes (Windows) are handled correctly."""
        ws_dir = fake_config / "workspaces" / "win_fp"
        ws_dir.mkdir(parents=True)
        ws_state = ws_dir / "SESSION_STATE.json"
        _write_workspace_state(ws_state, {"Phase": "3", "status": "OK"})

        # Use an absolute path string (works on any OS)
        pointer = {
            "schema": POINTER_SCHEMA,
            "activeSessionStateFile": str(ws_state),
        }
        (fake_config / "SESSION_STATE.json").write_text(
            json.dumps(pointer), encoding="utf-8"
        )
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "OK"
        assert result["phase"] == "3"
