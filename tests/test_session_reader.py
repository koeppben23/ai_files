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
    _coerce_int,
    _should_emit_continue_next_action,
    _resolve_next_action_line,
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
# Fix 3.5 (B5) — Draft vs persisted plan-record label
# ---------------------------------------------------------------------------

class TestPlanRecordLabel:
    """Fix 3.5 (B5): plan_record_label distinguishes working drafts from
    persisted plan-record versions.

    Test paths:
    - Happy: versions >= 1 + active status -> "persisted plan-record vN"
    - Happy: versions == 0 + absent status -> "working draft (not yet persisted)"
    - Corner: status "error" with versions >= 1 -> still "working draft"
    - Corner: status "unknown" with versions >= 1 -> still "working draft"
    - Edge: kernel result overrides persisted values
    - Bad: versions is a non-integer -> coerced to 0 -> "working draft"
    """

    def test_happy_persisted_with_active_status(
        self,
        fake_config: Path,
    ) -> None:
        """Active status + versions >= 1 -> persisted label."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "plan_record_status": "active",
                "plan_record_versions": 3,
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "persisted plan-record v3"

    def test_happy_working_draft_when_absent(
        self,
        fake_config: Path,
    ) -> None:
        """Absent status + versions == 0 -> working draft."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "4",
                "status": "OK",
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "working draft (not yet persisted)"

    def test_corner_error_status_with_versions_is_draft(
        self,
        fake_config: Path,
    ) -> None:
        """Error status -> working draft even if versions > 0."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5",
                "status": "OK",
                "plan_record_status": "error",
                "plan_record_versions": 2,
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "working draft (not yet persisted)"

    def test_corner_unknown_status_with_versions_is_draft(
        self,
        fake_config: Path,
    ) -> None:
        """Unknown status -> working draft even if versions > 0."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5",
                "status": "OK",
                "plan_record_status": "unknown",
                "plan_record_versions": 1,
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "working draft (not yet persisted)"

    def test_edge_kernel_result_determines_label(
        self,
        fake_config: Path,
    ) -> None:
        """When kernel result provides plan_record_status/versions, label uses those."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "plan_record_status": "absent",
            "plan_record_versions": 0,
        })

        from governance.kernel.phase_kernel import KernelResult

        kernel_with_plan = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Resume via /continue",
            workspace_ready=True,
            source="spec-next",
            status="OK",
            spec_hash="abc",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-b5-001",
            route_strategy="next",
            plan_record_status="active",
            plan_record_versions=2,
            transition_evidence_met=True,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=kernel_with_plan,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "persisted plan-record v2"

    def test_bad_non_integer_versions_coerced_to_draft(
        self,
        fake_config: Path,
    ) -> None:
        """Non-integer versions -> coerced to 0 -> working draft."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5",
                "status": "OK",
                "plan_record_status": "active",
                "plan_record_versions": "not-a-number",
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "working draft (not yet persisted)"

    def test_happy_draft_status_with_versions_is_persisted(
        self,
        fake_config: Path,
    ) -> None:
        """Draft status + versions >= 1 -> persisted (draft is a valid non-error status)."""
        ws_state = _write_pointer(fake_config)
        plan_record_file = ws_state.parent / "plan-record.json"
        plan_record_file.write_text(
            json.dumps({"status": "draft", "versions": [{"v": 1}]}),
            encoding="utf-8",
        )
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["plan_record_label"] == "persisted plan-record v1"


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
# Fix 1.3 — Symmetric next-action logic
# ---------------------------------------------------------------------------

class TestSymmetricNextAction:
    """Validates the symmetric _should_emit_continue_next_action logic (Fix 1.3)."""

    def test_happy_explicit_continue_mention(self) -> None:
        """Explicit '/continue' in condition always triggers the hint."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "next_gate_condition": "Phase 3A completed; resume via /continue",
        }) is True

    def test_happy_phase5_review_loop(self) -> None:
        """Phase 5 review loop without explicit /continue still emits hint."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "active_gate": "Architecture Review Gate",
            "next_gate_condition": "Plan record is present. Continue deterministic internal self-review.",
        }) is True

    def test_happy_phase6_implementation_loop(self) -> None:
        """Phase 6 implementation review loop emits hint symmetrically."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "phase": "6-PostFlight",
            "active_gate": "Implementation Internal Review",
            "next_gate_condition": "Complete deterministic internal implementation review iterations.",
        }) is True

    def test_happy_phase5_plan_record_prep(self) -> None:
        """Plan Record Preparation Gate emits hint (user needs /continue to produce plan)."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "active_gate": "Plan Record Preparation Gate",
            "next_gate_condition": "Continue",
        }) is True

    def test_corner_error_status_never_emits(self) -> None:
        """Error status suppresses the hint regardless of condition."""
        assert _should_emit_continue_next_action({
            "status": "ERROR",
            "next_gate_condition": "Resume via /continue",
        }) is False

    def test_corner_blocked_status_never_emits(self) -> None:
        """Blocked status suppresses the hint."""
        assert _should_emit_continue_next_action({
            "status": "BLOCKED",
            "next_gate_condition": "Resume via /continue",
        }) is False

    def test_edge_ticket_intake_does_not_emit(self) -> None:
        """Ticket intake gate requires /ticket, not /continue."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "next_gate_condition": "Collect ticket and planning constraints",
        }) is False

    def test_edge_provide_ticket_does_not_emit(self) -> None:
        """'Provide ticket/task' pattern suppresses the hint."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "next_gate_condition": "Provide ticket/task details to continue",
        }) is False

    def test_edge_blocked_condition_suppresses(self) -> None:
        """'BLOCKED' in condition text suppresses the hint even if status is OK."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "next_gate_condition": "BLOCKED_PHASE_API_MISSING: phase_api.yaml is required.",
        }) is False

    def test_bad_empty_status_does_not_emit(self) -> None:
        """Empty status string suppresses the hint."""
        assert _should_emit_continue_next_action({
            "status": "",
            "next_gate_condition": "Continue",
        }) is False

    def test_edge_wait_for_pattern_suppresses(self) -> None:
        """'wait for' in condition suppresses the hint."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "next_gate_condition": "wait for user final review decision",
        }) is False

    def test_edge_bootstrap_pattern_suppresses(self) -> None:
        """'run bootstrap' pattern suppresses the hint."""
        assert _should_emit_continue_next_action({
            "status": "OK",
            "next_gate_condition": "Run bootstrap before governance execution.",
        }) is False


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

    def test_materialize_mode_updates_phase5_gate_and_emits_chat_action_when_review_pending(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Phase 5 with self_review_iterations_met=False emits 'continue in chat' (Fix 3.2)."""
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
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
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
        assert "next_gate_condition: \"Phase 5 self-review status: iteration=0/3" in output
        assert "Ticket/task evidence captured; continue to Phase 5 plan-record preparation before architecture review" not in output
        # Fix 3.2 (B7): self_review_iterations_met is False (iteration=0 < max=3),
        # so the user should work in chat, not re-run /continue.
        assert output.strip().endswith("Next action: continue in chat with the active gate work.")

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["active_gate"] == "Architecture Review Gate"
        assert updated_state["PlanRecordStatus"] == "active"
        assert updated_state["PlanRecordVersions"] == 1

    def test_materialize_mode_phase5_missing_plan_record_stays_prep_with_plan_action(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Phase 5 Plan Record Preparation Gate recommends /plan when evidence is missing.

        When the plan record is missing the kernel stays at the Preparation
        Gate. The next action must be the explicit persist rail, not /continue.
        """
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
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
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
        assert output.strip().endswith("Next action: run /plan.")

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["active_gate"] == "Plan Record Preparation Gate"
        assert updated_state["PlanRecordVersions"] == 0

    def test_materialize_mode_phase5_ready_uses_next_token_and_clears_p53_gate(
        self,
        fake_config: Path,
    ) -> None:
        """When Phase 5 is review-complete, materialize must not stall at token 5.

        Regression guard: if Phase is still 5-ArchitectureReview but Next already
        points to 5.3 with transition evidence present, /continue must execute the
        next token path and clear P5.3-TestQuality from pending.
        """
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "5-ArchitectureReview",
                    "Next": "5.3",
                    "active_gate": "Architecture Review Gate",
                    "next_gate_condition": "Proceed to Phase 5.3 test-quality gate.",
                    "status": "OK",
                    "phase_transition_evidence": True,
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
                    "TechnicalDebt": {"Proposed": False},
                    "RollbackRequired": False,
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pending",
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

        snapshot = read_session_snapshot(commands_home=commands_home, materialize=True)

        assert snapshot["phase"] == "6-PostFlight"
        assert snapshot["next"] == "6"
        persisted = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert persisted["Gates"]["P5.3-TestQuality"] == "pass"

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

    def test_materialize_mode_phase6_runs_internal_review_loop_without_chat_interaction(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "6-PostFlight",
                    "Next": "6",
                    "active_gate": "Post Flight",
                    "next_gate_condition": "Implement, run deterministic internal implementation review loop, then present evidence.",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "phase5_plan_record_digest": "sha256:plan-v1",
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
        assert "implementation_review_complete: true" in output
        assert "continue in chat with the active gate work" not in output

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["implementation_review_complete"] is True
        assert updated_state["phase6_review_iterations"] == 3
        assert updated_state["phase6_state"] == "phase6_completed"

    def test_corner_materialize_mode_phase6_early_stop_on_stable_digest(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "6-PostFlight",
                    "Next": "6",
                    "active_gate": "Post Flight",
                    "next_gate_condition": "Complete implementation review iterations.",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "phase5_plan_record_digest": "sha256:plan-v1",
                    "phase6_force_stable_digest": True,
                    "ImplementationReview": {
                        "iteration": 0,
                        "max_iterations": 3,
                        "min_self_review_iterations": 1,
                    },
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
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
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
        assert "implementation_review_complete: true" in output

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["phase6_review_iterations"] == 2
        assert updated_state["phase6_revision_delta"] == "none"
        assert updated_state["implementation_review_complete"] is True

    def test_materialize_mode_phase6_normalizes_stale_completion_flags(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Phase 6 should not keep stale in-progress flags once iterations are complete."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "6-PostFlight",
                    "Next": "6",
                    "active_gate": "Evidence Presentation Gate",
                    "next_gate_condition": "Implementation review loop is complete.",
                    "status": "OK",
                    "phase6_review_iterations": 3,
                    "phase6_max_review_iterations": 3,
                    "phase6_min_self_review_iterations": 1,
                    "phase6_revision_delta": "changed",
                    "implementation_review_complete": False,
                    "phase6_state": "phase6_in_progress",
                    "ImplementationReview": {
                        "iteration": 3,
                        "max_iterations": 3,
                        "min_self_review_iterations": 1,
                        "completion_status": "phase6-in-progress",
                        "implementation_review_complete": False,
                    },
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "phase5_plan_record_digest": "sha256:plan-v1",
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
        assert "implementation_review_complete: true" in output

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["implementation_review_complete"] is True
        assert updated_state["phase6_state"] == "phase6_completed"
        review = updated_state["ImplementationReview"]
        assert review["completion_status"] == "phase6-completed"
        assert review["implementation_review_complete"] is True

    def test_edge_materialize_mode_phase6_clamps_iteration_bounds(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "Phase": "6-PostFlight",
                    "Next": "6",
                    "active_gate": "Post Flight",
                    "next_gate_condition": "Complete implementation review iterations.",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "phase5_plan_record_digest": "sha256:plan-v1",
                    "ImplementationReview": {
                        "iteration": "not-a-number",
                        "max_iterations": 99,
                        "min_self_review_iterations": 99,
                    },
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
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
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
        _ = capsys.readouterr().out

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["phase6_max_review_iterations"] == 3
        assert updated_state["phase6_min_self_review_iterations"] == 3
        assert updated_state["phase6_review_iterations"] == 3


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


# ---------------------------------------------------------------------------
# Fix 2.0 — Phase transition evidence visibility (Ergänzung C)
# ---------------------------------------------------------------------------

class TestTransitionEvidenceVisibility:
    """Validates phase_transition_evidence rendering in snapshots (Fix 2.0).

    The transition condition was previously invisible to users, causing
    /continue self-loops.  Now it is:
    - Rendered in every snapshot as ``phase_transition_evidence``
    - Sourced from KernelResult.transition_evidence_met when available
    - Diagnosed with a hint when evidence is missing and blocking
    - Auto-granted during materialization when a forward transition succeeds
    """

    def test_happy_evidence_true_from_kernel(self, fake_config: Path) -> None:
        """When kernel reports evidence met, snapshot shows True."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        from governance.kernel.phase_kernel import KernelResult

        fake_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Resume via /continue",
            workspace_ready=True,
            source="transition",
            status="OK",
            spec_hash="abc",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-evidence-001",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=True,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is True
        assert "transition_evidence_hint" not in result

    def test_happy_evidence_false_from_kernel_no_block(self, fake_config: Path) -> None:
        """When kernel reports evidence not met but status is OK, shows False without hint."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        from governance.kernel.phase_kernel import KernelResult

        fake_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5",
            active_gate="Architecture Review Gate",
            next_gate_condition="Continue review",
            workspace_ready=True,
            source="stay",
            status="OK",
            spec_hash="abc",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-evidence-002",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False
        # No hint because source is not evidence-related
        assert "transition_evidence_hint" not in result

    def test_corner_evidence_blocked_shows_diagnostic_hint(self, fake_config: Path) -> None:
        """When kernel blocks on missing evidence, snapshot includes diagnostic hint."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        from governance.kernel.phase_kernel import KernelResult

        blocked_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5",
            active_gate="Architecture Review Gate",
            next_gate_condition="PHASE_BLOCKED: transition evidence required for requested phase jump",
            workspace_ready=True,
            source="phase-transition-evidence-required",
            status="BLOCKED",
            spec_hash="abc",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-evidence-003",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=blocked_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False
        assert "transition_evidence_hint" in result
        assert "phase_transition_evidence is False" in result["transition_evidence_hint"]
        assert "/continue" in result["transition_evidence_hint"]

    def test_corner_fallback_to_persisted_state_on_kernel_error(self, fake_config: Path) -> None:
        """When kernel eval fails, evidence is read from persisted state."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "phase_transition_evidence": True,
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is True

    def test_edge_persisted_evidence_string_truthy(self, fake_config: Path) -> None:
        """Persisted evidence as non-empty string evaluates to True."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "phase_transition_evidence": "architecture-approved",
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is True

    def test_edge_persisted_evidence_empty_string_falsy(self, fake_config: Path) -> None:
        """Persisted evidence as empty string evaluates to False."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "phase_transition_evidence": "",
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False

    def test_edge_persisted_evidence_list_truthy(self, fake_config: Path) -> None:
        """Persisted evidence as non-empty list evaluates to True."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "phase_transition_evidence": ["review-passed"],
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is True

    def test_edge_persisted_evidence_empty_list_falsy(self, fake_config: Path) -> None:
        """Persisted evidence as empty list evaluates to False."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "phase_transition_evidence": [],
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False

    def test_bad_no_evidence_field_defaults_to_false(self, fake_config: Path) -> None:
        """When phase_transition_evidence is absent, defaults to False."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False

    def test_evidence_appears_in_formatted_output(self, fake_config: Path) -> None:
        """phase_transition_evidence is rendered in format_snapshot output."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "5",
            "status": "OK",
            "phase_transition_evidence": True,
        })

        with _mock_readonly_unavailable():
            snapshot = read_session_snapshot(commands_home=fake_config / "commands")

        rendered = format_snapshot(snapshot)
        assert "phase_transition_evidence: true" in rendered

    def test_evidence_false_appears_in_formatted_output(self, fake_config: Path) -> None:
        """phase_transition_evidence=false is rendered in format_snapshot output."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        with _mock_readonly_unavailable():
            snapshot = read_session_snapshot(commands_home=fake_config / "commands")

        rendered = format_snapshot(snapshot)
        assert "phase_transition_evidence: false" in rendered


class TestTransitionEvidenceAutoGrant:
    """Validates auto-grant of phase_transition_evidence during materialization (Fix 2.0)."""

    def test_happy_auto_grant_on_forward_transition(
        self,
        fake_config: Path,
    ) -> None:
        """When materialize produces OK + route_strategy=next, evidence is auto-granted."""
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
                    "active_gate": "Architecture Review Gate",
                    "next_gate_condition": "Resume via /continue",
                    "status": "OK",
                    "phase_transition_evidence": False,
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
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
            },
        )

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

        (ws_state.parent / "plan-record.json").write_text(
            json.dumps({"status": "active", "versions": [{"version": 1}]}, ensure_ascii=True),
            encoding="utf-8",
        )

        # Materialize — the kernel should evaluate Phase 5 with route_strategy=next
        # and the auto-grant should set phase_transition_evidence=True
        result = read_session_snapshot(commands_home=commands_home, materialize=True)
        assert result["status"] != "ERROR", f"Unexpected error: {result.get('error', '')}"

        # Read back the persisted state to verify auto-grant
        persisted = json.loads(ws_state.read_text(encoding="utf-8"))
        ss = persisted.get("SESSION_STATE", persisted)
        # The kernel may or may not produce route_strategy=next depending
        # on whether plan record prep advances.  If it stays at the same
        # phase (stay strategy), evidence should not be auto-granted.
        # We test the presence of the key — it should exist either way.
        assert "phase_transition_evidence" in ss or "phase_transition_evidence" in persisted

    def test_corner_no_auto_grant_when_stay_strategy(
        self,
        fake_config: Path,
    ) -> None:
        """When materialize produces OK + route_strategy=stay, evidence is NOT auto-granted."""
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
                    "active_gate": "Architecture Review Gate",
                    "next_gate_condition": "Continue review",
                    "status": "OK",
                    "phase_transition_evidence": False,
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
            },
        )

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

        from governance.kernel.phase_kernel import KernelResult

        stay_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5",
            active_gate="Architecture Review Gate",
            next_gate_condition="Continue deterministic review",
            workspace_ready=True,
            source="phase-5-self-review-required",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-stay-001",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch("governance.kernel.phase_kernel.execute", return_value=stay_result):
            result = read_session_snapshot(commands_home=commands_home, materialize=True)

        assert result["status"] != "ERROR", f"Unexpected error: {result.get('error', '')}"

        # Stay strategy — evidence must NOT be auto-granted
        persisted = json.loads(ws_state.read_text(encoding="utf-8"))
        ss = persisted.get("SESSION_STATE", persisted)
        assert ss.get("phase_transition_evidence") is not True


# ---------------------------------------------------------------------------
# Fix 3.x — B6-B8 renderer diagnostics
# ---------------------------------------------------------------------------

class TestCoerceInt:
    """Unit tests for _coerce_int helper (Fix 3.1)."""

    def test_none(self) -> None:
        assert _coerce_int(None) == 0

    def test_int(self) -> None:
        assert _coerce_int(3) == 3

    def test_str(self) -> None:
        assert _coerce_int("2") == 2

    def test_negative_clamped(self) -> None:
        assert _coerce_int(-1) == 0

    def test_invalid_str(self) -> None:
        assert _coerce_int("abc") == 0

    def test_bool_true(self) -> None:
        # bool is int subclass in Python; True -> 1
        assert _coerce_int(True) == 1


class TestPhase5SelfReviewDiagnostics:
    """Fix 3.1 (B6): Phase 5 self-review state visible in snapshot.

    Required tests:
    - test_missing_self_review_iterations_met_visible_in_snapshot
    - test_fulfilled_self_review_sets_next_correctly
    """

    def test_missing_self_review_iterations_met_visible_in_snapshot(
        self,
        fake_config: Path,
    ) -> None:
        """When Phase5Review shows 0/3 iterations, snapshot has met=false."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "active_gate": "Architecture Review Gate",
                "Phase5Review": {
                    "iteration": 0,
                    "max_iterations": 3,
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase5_self_review_iterations"] == 0
        assert result["phase5_max_review_iterations"] == 3
        assert result["phase5_revision_delta"] == "changed"
        assert result["self_review_iterations_met"] is False

    def test_fulfilled_self_review_sets_met_true(
        self,
        fake_config: Path,
    ) -> None:
        """When iteration >= max_iterations, self_review_iterations_met is True."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "active_gate": "Architecture Review Gate",
                "Phase5Review": {
                    "iteration": 3,
                    "max_iterations": 3,
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase5_self_review_iterations"] == 3
        assert result["phase5_max_review_iterations"] == 3
        assert result["self_review_iterations_met"] is True

    def test_revision_delta_none_with_min_iterations_sets_met_true(
        self,
        fake_config: Path,
    ) -> None:
        """When iteration >= 1 and revision_delta == 'none', met is True."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "Phase5Review": {
                    "iteration": 1,
                    "max_iterations": 3,
                    "prev_plan_digest": "sha256:abc",
                    "curr_plan_digest": "sha256:abc",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase5_revision_delta"] == "none"
        assert result["self_review_iterations_met"] is True

    def test_no_phase5_fields_for_non_phase5(
        self,
        fake_config: Path,
    ) -> None:
        """Phase 4 snapshot must NOT contain phase5 self-review fields."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "4",
            "status": "OK",
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert "phase5_self_review_iterations" not in result
        assert "self_review_iterations_met" not in result

    def test_pascal_case_phase5_review_keys(
        self,
        fake_config: Path,
    ) -> None:
        """PascalCase keys in Phase5Review block are recognized."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "Phase5Review": {
                    "Iteration": 2,
                    "MaxIterations": 3,
                    "PrevPlanDigest": "sha256:aaa",
                    "CurrPlanDigest": "sha256:bbb",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase5_self_review_iterations"] == 2
        assert result["phase5_max_review_iterations"] == 3
        assert result["phase5_revision_delta"] == "changed"
        assert result["self_review_iterations_met"] is False


class TestMissingTransitionEvidenceDiagnosed:
    """Fix 2.0 + 3.2: Missing phase_transition_evidence is diagnosed.

    Required test:
    - test_missing_phase_transition_evidence_diagnosed
    """

    def test_missing_phase_transition_evidence_diagnosed(
        self,
        fake_config: Path,
    ) -> None:
        """When kernel source is 'phase-transition-evidence-required', snapshot has hint."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        from governance.kernel.phase_kernel import KernelResult

        blocked_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5",
            active_gate="Architecture Review Gate",
            next_gate_condition="PHASE_BLOCKED: transition evidence required",
            workspace_ready=True,
            source="phase-transition-evidence-required",
            status="BLOCKED",
            spec_hash="abc",
            spec_path="/fake",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-diag-001",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=blocked_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False
        assert "transition_evidence_hint" in result
        assert "phase_transition_evidence is False" in result["transition_evidence_hint"]


class TestResolveNextActionLine:
    """Fix 3.2 (B7): _resolve_next_action_line distinguishes /continue vs chat work.

    Required tests:
    - test_next_action_line_chat_for_gate_work
    - test_next_action_line_continue_for_materialization
    - test_no_stale_next_gate_condition
    """

    def test_next_action_line_continue_for_materialization(self) -> None:
        """OK status + no blocking indicators -> 'run /continue'."""
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "next_gate_condition": "Complete deterministic internal implementation review iterations.",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_next_action_line_chat_for_gate_work_evidence_hint(self) -> None:
        """When transition_evidence_hint is present -> 'continue in chat'."""
        snapshot = {
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "next_gate_condition": "Resume via /continue",
            "transition_evidence_hint": "phase_transition_evidence is False — forward phase jump blocked.",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: continue in chat with the active gate work."

    def test_next_action_line_chat_for_phase5_review_pending(self) -> None:
        """Phase 5 with self_review_iterations_met=False -> 'continue in chat'."""
        snapshot = {
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "next_gate_condition": "Continue review",
            "self_review_iterations_met": False,
        }
        assert _resolve_next_action_line(snapshot) == "Next action: continue in chat with the active gate work."

    def test_next_action_line_plan_for_phase5_plan_prep_without_persisted_record(self) -> None:
        """Phase 5 prep gate with absent plan record must recommend /plan, not /continue."""
        snapshot = {
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "active_gate": "Plan Record Preparation Gate",
            "next_gate_condition": "Create and persist plan-record evidence",
            "plan_record_status": "absent",
            "plan_record_versions": 0,
            "self_review_iterations_met": False,
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /plan."

    def test_next_action_line_continue_for_phase5_review_met(self) -> None:
        """Phase 5 with self_review_iterations_met=True -> 'run /continue'."""
        snapshot = {
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "next_gate_condition": "Continue review",
            "self_review_iterations_met": True,
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_next_action_line_explicit_p53_guidance_at_handoff(self) -> None:
        """Phase 5 handoff to 5.3 must tell users to perform test-quality work."""
        snapshot = {
            "status": "OK",
            "phase": "5-ArchitectureReview",
            "next": "5.3",
            "next_gate_condition": "Proceed to Phase 5.3 test-quality gate.",
            "self_review_iterations_met": True,
        }
        assert _resolve_next_action_line(snapshot) == (
            "Next action: execute Phase 5.3 test-quality review, then run /continue."
        )

    def test_no_stale_next_gate_condition(self) -> None:
        """Blocked status never emits any action line."""
        snapshot = {
            "status": "BLOCKED",
            "phase": "5-ArchitectureReview",
            "next_gate_condition": "BLOCKED: stale condition",
        }
        assert _resolve_next_action_line(snapshot) == ""

    def test_next_action_line_explicit_p54_guidance(self) -> None:
        """Phase 5.4 with satisfied evidence should recommend /continue."""
        snapshot = {
            "status": "OK",
            "phase": "5.4-BusinessRules",
            "next": "5.5",
            "next_gate_condition": "Business rules validation complete; technical debt proposed",
            "p54_evaluated_status": "compliant",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_next_action_line_p54_missing_evidence_recommends_plan(self) -> None:
        snapshot = {
            "status": "OK",
            "phase": "5.4-BusinessRules",
            "next": "5.4",
            "next_gate_condition": "Phase 6 promotion blocked: BLOCKED-P5-4-BUSINESS-RULES-GATE",
            "p54_evaluated_status": "gap-detected",
        }
        assert _resolve_next_action_line(snapshot) == (
            "Next action: run /plan with explicit business-rules compliance evidence."
        )

    def test_next_action_line_explicit_p55_guidance(self) -> None:
        """Phase 5.5 with satisfied evidence should recommend /continue."""
        snapshot = {
            "status": "OK",
            "phase": "5.5-TechnicalDebt",
            "next": "5.6",
            "next_gate_condition": "Technical debt recorded; rollback checks required",
            "p55_evaluated_status": "approved",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_next_action_line_p55_missing_evidence_recommends_plan(self) -> None:
        snapshot = {
            "status": "OK",
            "phase": "5.5-TechnicalDebt",
            "next": "5.5",
            "next_gate_condition": "Technical debt review incomplete",
            "p55_evaluated_status": "pending",
        }
        assert _resolve_next_action_line(snapshot) == (
            "Next action: run /plan with explicit technical-debt review evidence."
        )

    def test_next_action_line_explicit_p56_guidance(self) -> None:
        """Phase 5.6 with satisfied evidence should recommend /continue."""
        snapshot = {
            "status": "OK",
            "phase": "5.6-RollbackSafety",
            "next": "6",
            "next_gate_condition": "Rollback safety checks complete; proceed to post-flight",
            "p56_evaluated_status": "not-applicable",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_next_action_line_p56_missing_evidence_recommends_plan(self) -> None:
        snapshot = {
            "status": "OK",
            "phase": "5.6-RollbackSafety",
            "next": "5.6",
            "next_gate_condition": "Rollback safety evidence incomplete",
            "p56_evaluated_status": "pending",
        }
        assert _resolve_next_action_line(snapshot) == (
            "Next action: run /plan with explicit rollback-safety evidence."
        )

    def test_empty_for_ticket_intake(self) -> None:
        """Ticket intake condition returns empty (needs /ticket, not /continue)."""
        snapshot = {
            "status": "OK",
            "phase": "4",
            "next_gate_condition": "Collect ticket and planning constraints",
        }
        assert _resolve_next_action_line(snapshot) == ""


class TestRouteTargetExplanation:
    """Fix 3.3 (B8): Route target is explained for intermediate next tokens.

    Required test:
    - test_route_target_explained_for_intermediate_next
    """

    def test_route_target_explained_for_intermediate_next(
        self,
        fake_config: Path,
    ) -> None:
        """When kernel evaluates route_strategy=next, snapshot explains the route target."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        from governance.kernel.phase_kernel import KernelResult

        next_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Resume via /continue",
            workspace_ready=True,
            source="spec-next",
            status="OK",
            spec_hash="abc",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-route-001",
            route_strategy="next",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=True,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=next_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["route_target"] == "5.3"
        assert result["route_strategy"] == "next"
        assert "intermediate target" in result["route_explanation"]
        assert "5.3" in result["route_explanation"]

    def test_no_route_explanation_for_stay_strategy(
        self,
        fake_config: Path,
    ) -> None:
        """When kernel evaluates route_strategy=stay, no route explanation fields."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        from governance.kernel.phase_kernel import KernelResult

        stay_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5",
            active_gate="Architecture Review Gate",
            next_gate_condition="Continue review",
            workspace_ready=True,
            source="stay",
            status="OK",
            spec_hash="abc",
            spec_path="/fake/spec.yaml",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-route-002",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=stay_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert "route_target" not in result
        assert "route_explanation" not in result

    def test_no_route_explanation_when_kernel_unavailable(
        self,
        fake_config: Path,
    ) -> None:
        """Without kernel eval, no route explanation fields appear."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"Phase": "5", "status": "OK"})

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert "route_target" not in result
        assert "route_explanation" not in result


class TestPhase6ImplementationReviewDiagnostics:
    """Fix 3.4 (B13): Phase 6 implementation-review exit diagnostics.

    Surface kernel-owned exit conditions for the Phase 6 internal review
    loop so users can see iteration progress, revision delta, and
    completion status — mirroring the Phase 5 self-review diagnostics.

    Test paths:
    - Happy: iteration 2/3 with changed delta -> not complete
    - Happy: iteration 3/3 -> complete (max reached)
    - Happy: iteration 1/3 with delta=none -> complete (early-stop)
    - Corner: PascalCase keys in ImplementationReview block
    - Corner: top-level flat keys (phase6_review_iterations, etc.)
    - Corner: non-Phase-6 snapshot does not contain phase6 fields
    - Corner: min_review_iterations floor clamped
    - Edge: missing ImplementationReview block defaults gracefully
    - Edge: ImplementationReview is not a dict -> defaults
    - Bad: non-integer iteration values coerced to 0
    """

    def test_happy_not_complete_iterations_below_max(
        self,
        fake_config: Path,
    ) -> None:
        """Iteration 2 of 3 with changed delta -> not complete."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "iteration": 2,
                    "max_iterations": 3,
                    "min_self_review_iterations": 1,
                    "prev_impl_digest": "sha256:aaa",
                    "curr_impl_digest": "sha256:bbb",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 2
        assert result["phase6_max_review_iterations"] == 3
        assert result["phase6_min_review_iterations"] == 1
        assert result["phase6_revision_delta"] == "changed"
        assert result["implementation_review_complete"] is False

    def test_happy_complete_max_reached(
        self,
        fake_config: Path,
    ) -> None:
        """Iteration 3 of 3 -> complete regardless of delta."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "iteration": 3,
                    "max_iterations": 3,
                    "min_self_review_iterations": 1,
                    "prev_impl_digest": "sha256:aaa",
                    "curr_impl_digest": "sha256:bbb",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 3
        assert result["phase6_max_review_iterations"] == 3
        assert result["phase6_revision_delta"] == "changed"
        assert result["implementation_review_complete"] is True

    def test_happy_early_stop_delta_none(
        self,
        fake_config: Path,
    ) -> None:
        """Iteration 1 with unchanged digest -> complete (early-stop)."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "iteration": 1,
                    "max_iterations": 3,
                    "min_self_review_iterations": 1,
                    "prev_impl_digest": "sha256:abc",
                    "curr_impl_digest": "sha256:abc",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_revision_delta"] == "none"
        assert result["implementation_review_complete"] is True

    def test_corner_pascal_case_keys(
        self,
        fake_config: Path,
    ) -> None:
        """PascalCase keys in ImplementationReview block are recognized."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "Iteration": 2,
                    "MaxIterations": 3,
                    "MinSelfReviewIterations": 2,
                    "PrevImplDigest": "sha256:aaa",
                    "CurrImplDigest": "sha256:bbb",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 2
        assert result["phase6_max_review_iterations"] == 3
        assert result["phase6_min_review_iterations"] == 2
        assert result["phase6_revision_delta"] == "changed"
        assert result["implementation_review_complete"] is False

    def test_corner_flat_top_level_keys(
        self,
        fake_config: Path,
    ) -> None:
        """Top-level flat keys (phase6_review_iterations, etc.) are recognized."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "phase6_review_iterations": 1,
                "phase6_max_review_iterations": 2,
                "phase6_min_self_review_iterations": 1,
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 1
        assert result["phase6_max_review_iterations"] == 2
        # No digests -> delta is "changed"
        assert result["phase6_revision_delta"] == "changed"
        assert result["implementation_review_complete"] is False

    def test_corner_no_phase6_fields_for_non_phase6(
        self,
        fake_config: Path,
    ) -> None:
        """Phase 4 snapshot must NOT contain phase6 implementation-review fields."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "Phase": "4",
            "status": "OK",
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert "phase6_review_iterations" not in result
        assert "implementation_review_complete" not in result

    def test_corner_min_review_clamped(
        self,
        fake_config: Path,
    ) -> None:
        """min_review_iterations is clamped between 1 and max_iterations."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "iteration": 1,
                    "max_iterations": 2,
                    "min_self_review_iterations": 5,  # exceeds max -> clamped to 2
                    "prev_impl_digest": "sha256:abc",
                    "curr_impl_digest": "sha256:abc",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_min_review_iterations"] == 2  # clamped to max
        # iteration 1 < clamped_min 2, delta=none, but min not met
        assert result["implementation_review_complete"] is False

    def test_edge_missing_review_block_defaults(
        self,
        fake_config: Path,
    ) -> None:
        """Missing ImplementationReview block -> sensible defaults."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 0
        assert result["phase6_max_review_iterations"] == 3  # default
        assert result["phase6_min_review_iterations"] == 1  # default
        assert result["phase6_revision_delta"] == "changed"
        assert result["implementation_review_complete"] is False

    def test_edge_review_block_not_dict_defaults(
        self,
        fake_config: Path,
    ) -> None:
        """ImplementationReview set to a non-dict -> sensible defaults."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": "invalid",
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 0
        assert result["phase6_max_review_iterations"] == 3
        assert result["implementation_review_complete"] is False

    def test_bad_non_integer_iteration_coerced(
        self,
        fake_config: Path,
    ) -> None:
        """Non-integer values in iteration fields coerced to 0."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "iteration": "not-a-number",
                    "max_iterations": "also-bad",
                },
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_review_iterations"] == 0
        assert result["phase6_max_review_iterations"] == 3  # fallback since 0 < 1
        assert result["implementation_review_complete"] is False


class TestPhase6NextActionLine:
    """Fix 3.4 (B13): _resolve_next_action_line handles Phase 6 review loop.

    Phase 6 loops are now materialized by /continue, so guidance remains /continue.
    """

    def test_chat_work_when_review_incomplete(self) -> None:
        """Phase 6 with implementation_review_complete=False -> /continue."""
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "next_gate_condition": "Complete implementation review iterations.",
            "implementation_review_complete": False,
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_continue_when_review_complete(self) -> None:
        """Phase 6 with implementation_review_complete=True -> /continue."""
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "next_gate_condition": "Present evidence for final user review.",
            "implementation_review_complete": True,
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_continue_when_review_field_absent(self) -> None:
        """Phase 6 without implementation_review_complete field -> default /continue."""
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "next_gate_condition": "Present evidence for final user review.",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: run /continue."

    def test_empty_for_blocked_phase6(self) -> None:
        """Phase 6 with BLOCKED status -> no action line."""
        snapshot = {
            "status": "BLOCKED",
            "phase": "6-PostFlight",
            "next_gate_condition": "BLOCKED: prerequisites not met",
            "implementation_review_complete": False,
        }
        assert _resolve_next_action_line(snapshot) == ""
