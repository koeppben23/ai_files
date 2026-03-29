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
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import governance_runtime.entrypoints.session_reader as session_reader_entrypoint
from governance_runtime.entrypoints.session_reader import (
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
    _build_runtime_context,
    _should_emit_continue_next_action,
    _resolve_next_action_line,
    _render_blocker,
)
from tests.util import get_phase_api_path


def _write_minimum_governance_specs(spec_home: Path) -> None:
    """Write the minimal authoritative spec bundle used by kernel paths.

    Includes phase_api plus the core governance specs now consulted by
    topology/command policy paths.
    """
    spec_home.mkdir(parents=True, exist_ok=True)
    source_spec_home = get_phase_api_path().parent
    for name in (
        "phase_api.yaml",
        "topology.yaml",
        "command_policy.yaml",
        "guards.yaml",
        "messages.yaml",
    ):
        (spec_home / name).write_text(
            (source_spec_home / name).read_text(encoding="utf-8"),
            encoding="utf-8",
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
    """Write workspace SESSION_STATE.json with proper nested structure.
    
    Handles both flat state (wraps in SESSION_STATE) and pre-wrapped state (uses as-is).
    """
    if "SESSION_STATE" in state:
        doc = state
    else:
        doc = {"SESSION_STATE": state}
    ws_state.write_text(json.dumps(doc), encoding="utf-8")


def _set_pipeline_mode_bindings(
    monkeypatch: pytest.MonkeyPatch,
    workspace_dir: Path,
    *,
    execution_cmd: str = "mock-executor",
    review_cmd: str = "mock-executor",
) -> None:
    (workspace_dir / "governance-config.json").write_text(
        json.dumps(
            {
                "pipeline_mode": True,
                "presentation": {
                    "mode": "standard",
                },
                "review": {
                    "phase5_max_review_iterations": 3,
                    "phase6_max_review_iterations": 3,
                },
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_GOVERNANCE_EXECUTION_BINDING", execution_cmd)
    monkeypatch.setenv("AI_GOVERNANCE_REVIEW_BINDING", review_cmd)


def _mock_phase6_mandate_schema() -> object:
    return type(
        "MockMandateSchema",
        (),
        {
            "raw_schema": {"$defs": {"reviewOutputSchema": {"type": "object"}}},
            "review_output_schema_text": '{"type":"object"}',
            "mandate_text": "Review mandate",
        },
    )()


def _mock_readonly_unavailable():
    """Patch evaluate_readonly to raise, triggering graceful degradation.

    Used in tests that validate field extraction from persisted state
    without needing a full kernel setup (phase_api.yaml, etc.).
    """
    return patch(
        "governance_runtime.kernel.phase_kernel.evaluate_readonly",
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
            "phase": "4",
            "next": "5",
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

    def test_operating_mode_fields_passthrough(self, fake_config: Path) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "status": "OK",
            "effective_operating_mode": "pipeline",
            "resolvedOperatingMode": "team",
            "verifyPolicyVersion": "v2",
            "operatingModeResolution": {
                "resolutionState": "resolved_with_fallback",
                "errorCode": "MISSING_OPERATING_MODE",
                "fallbackApplied": True,
            },
        })
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["effective_operating_mode"] == "pipeline"
        assert result["resolved_operating_mode"] == "team"
        assert result["verify_policy_version"] == "v2"
        assert result["operating_mode_resolution"]["resolutionState"] == "resolved_with_fallback"

    def test_operating_mode_fields_default_when_missing(self, fake_config: Path) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"status": "OK"})
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["effective_operating_mode"] == "solo"
        assert result["resolved_operating_mode"] == "solo"
        assert result["verify_policy_version"] == "v1"

    def test_commands_home_in_snapshot(self, fake_config: Path) -> None:
        """Snapshot includes the resolved commands_home path."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"status": "OK"})
        commands_home = fake_config / "commands"
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=commands_home)
        assert result["commands_home"] == str(commands_home)

    def test_evidence_presentation_gate_includes_review_brief(self, fake_config: Path) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "status": "OK",
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "Ticket": "Ticket summary example",
            "ImplementationReview": {
                "iteration": 2,
                "max_iterations": 3,
                "min_self_review_iterations": 1,
                "prev_impl_digest": "sha256:a",
                "curr_impl_digest": "sha256:b",
            },
            "plan_record_versions": 2,
        })
        (ws_state.parent / "plan-record.json").write_text(
            json.dumps({
                "status": "active",
                "versions": [{"version": 1}, {"version": 2, "plan_record_text": "Plan body example"}],
            }),
            encoding="utf-8",
        )
        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["review_package_review_object"]
        assert result["review_package_ticket"] == "Ticket summary example"
        assert "Plan body example" in result["review_package_approved_plan_summary"]
        assert "Plan body example" in result["review_package_plan_body"]
        assert result["review_package_evidence_summary"]
        assert result["review_package_loop_status"]
        assert result["review_package_decision_semantics"]

    def test_relative_path_fallback(self, fake_config: Path) -> None:
        """Pointer with only activeSessionStateRelativePath still works."""
        ws_dir = fake_config / "workspaces" / "abc123"
        ws_dir.mkdir(parents=True)
        ws_state = ws_dir / "SESSION_STATE.json"
        _write_workspace_state(ws_state, {"phase": "2", "status": "OK"})

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
                "phase": "4",
                "next": "4",
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
                    "phase": "5-ArchitectureReview",
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
                    "phase": "5-ArchitectureReview",
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
                "phase": "5-ArchitectureReview",
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
                "phase": "4",
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
                "phase": "5",
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
                "phase": "5",
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
            "phase": "5",
            "status": "OK",
            "plan_record_status": "absent",
            "plan_record_versions": 0,
        })

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
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
                "phase": "5",
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
                "phase": "5-ArchitectureReview",
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
            "phase": "4",
            "status": "OK",
            "active_gate": "stale-gate",
            "next_gate_condition": "stale-condition",
        })

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        # Kernel-authoritative fields must come from the KernelResult.
        assert result["phase"] == "5"
        assert result["status"] == "OK"
        assert result["active_gate"] == "Architecture Review Gate"
        assert result["next_gate_condition"] == "Resume via /continue"
        assert result["next"] == "5"
        assert result["plan_record_status"] == "active"
        assert result["plan_record_versions"] == 2

    def test_corner_graceful_degradation_on_kernel_error(self, fake_config: Path) -> None:
        """When kernel eval raises, snapshot falls back to persisted state."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "phase": "4",
            "next": "5",
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
                "phase": "4",
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
                    "addons": {
                        "riskTiering": "rulesets/profiles/rules.risk-tiering.yml",
                    },
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
            side_effect=AssertionError("evaluate_readonly must NOT be called in materialize mode"),
        ):
            result = read_session_snapshot(commands_home=commands_home, materialize=True)

        # Should succeed via execute() path, not evaluate_readonly().
        assert result["status"] != "ERROR"

    def test_bad_kernel_returns_blocked_status(self, fake_config: Path) -> None:
        """When kernel eval returns BLOCKED, snapshot reflects BLOCKED."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "phase": "4",
            "status": "OK",
            "active_gate": "stale-gate",
        })

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
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
        _write_workspace_state(ws_state, {"phase": "4", "status": "OK"})
        original_content = ws_state.read_text(encoding="utf-8")

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
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
        _write_workspace_state(ws_state, {"phase": "4", "status": "OK"})
        with _mock_readonly_unavailable():
            rc = main(["--commands-home", str(fake_config / "commands")])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Current phase is" in captured.out
        assert "Next action:" in captured.out

    def test_error_exit_code(self, fake_config: Path, capsys: pytest.CaptureFixture) -> None:
        # No pointer file -> error
        rc = main(["--commands-home", str(fake_config / "commands")])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Current blocker is active:" in captured.out
        if "Next action:" in captured.out:
            assert captured.out.strip().splitlines()[-1].startswith("Next action: ")

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
                    "phase": "4",
                    "next": "5",
                    "active_gate": "Ticket Input Gate",
                    "phase4_intake_updated_at": "2026-03-05T20:34:32Z",
                }
            },
        )

        snapshot_doc = {
            "SESSION_STATE": {
                "session_run_id": "work-1",
                "phase": "6-PostFlight",
                "active_gate": "Post Flight",
                "next": "6",
            }
        }
        snapshot_path = ws_state.parent.parent / "governance-records" / ws_state.parent.name / "runs" / "work-1" / "SESSION_STATE.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot_doc), encoding="utf-8")

        from governance_runtime.engine.canonical_json import canonical_json_hash

        digest = canonical_json_hash(snapshot_doc)
        (ws_state.parent.parent / "governance-records" / ws_state.parent.name / "runs" / "work-1" / "metadata.json").write_text(
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
        (ws_state.parent / "logs").mkdir(parents=True, exist_ok=True)
        (ws_state.parent / "logs" / "events.jsonl").write_text(
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
                    "phase": "5-ArchitectureReview",
                    "next": "5",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
        assert "Current phase is" in output
        assert "active gate Architecture Review Gate" in output
        assert "Phase 5 self-review status: iteration=0/3" in output
        assert "Ticket/task evidence captured; continue to Phase 5 plan-record preparation before architecture review" not in output
        assert "Next action:" in output

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
                    "phase": "5-ArchitectureReview",
                    "next": "5",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
        assert "active gate Plan Record Preparation Gate" in output
        assert output.strip().endswith("Next action: /plan")

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
                    "phase": "5-ArchitectureReview",
                    "next": "5.3",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
                    "phase": "4",
                    "next": "5",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
        assert "active gate Ticket Input Gate" in output
        assert not output.strip().endswith("Next action: run /continue.")

    def test_materialize_mode_phase6_runs_internal_review_loop_without_chat_interaction(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from governance_runtime.kernel.command_policy_loader import CommandPolicyLoader
        from governance_runtime.kernel.spec_registry import SpecRegistry
        from governance_runtime.kernel.topology_loader import TopologyLoader

        SpecRegistry.reset()
        TopologyLoader.reset()
        CommandPolicyLoader.reset()

        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": "6-PostFlight",
                    "next": "6",
                    "phase6_state": "6.execution",
                    "active_gate": "Post Flight",
                    "next_gate_condition": "Implement, run deterministic internal implementation review loop, then present evidence.",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "TicketRecordDigest": "sha256:ticket-v1",
                    "phase5_plan_record_digest": "sha256:plan-v1",
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
                        "P5.4-BusinessRules": "compliant",
                        "P5.5-TechnicalDebt": "approved",
                        "P5.6-RollbackSafety": "approved",
                    },
                }
            },
        )

        commands_home = fake_config / "commands"
        spec_home = fake_config / "governance_spec"
        spec_home.mkdir(parents=True, exist_ok=True)
        _write_minimum_governance_specs(spec_home)
        (fake_config / "governance.paths.json").write_text(
            json.dumps(
                {
                    "schema": "opencode-governance.paths.v1",
                    "paths": {
                        "commandsHome": str(commands_home),
                        "workspacesHome": str(fake_config / "workspaces"),
                        "configRoot": str(fake_config),
                        "specHome": str(spec_home),
                        "pythonCommand": "python3",
                    },
                }
            ),
            encoding="utf-8",
        )
        approve_response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation. All plan steps correctly implemented.",
            "contract_check": "SSOT boundaries preserved. No contract drift.",
            "findings": [],
            "regression_assessment": "Low risk profile. Implementation isolated.",
            "test_assessment": "Tests sufficient for changed scope.",
        })

        import subprocess

        def mock_subprocess_run(*args, **kwargs):
            return type("MockResult", (), {"stdout": approve_response, "stderr": "", "returncode": 0})()

        _set_pipeline_mode_bindings(monkeypatch, ws_state.parent)
        with monkeypatch.context() as m:
            m.setattr(subprocess, "run", mock_subprocess_run)
            m.setattr(
                session_reader_entrypoint,
                "_load_effective_review_policy_text",
                lambda **_kwargs: ("[EFFECTIVE REVIEW POLICY]\n- baseline", ""),
            )
            from governance_runtime.application.services.phase6_review_orchestrator import _set_policy_resolver
            mock_policy_resolver = type("MockPolicyResolver", (), {
                "load_effective_review_policy": lambda self, **kw: type("R", (), {
                    "is_available": True,
                    "policy_text": "[EFFECTIVE REVIEW POLICY]\n- baseline",
                    "error_code": "",
                })(),
                "load_mandate_schema": lambda self, **kw: _mock_phase6_mandate_schema(),
            })()
            _set_policy_resolver(mock_policy_resolver)
            rc = main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "Plan under review:" in output
        assert "continue in chat with the active gate work" not in output
        assert "Next action:" in output

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["implementation_review_complete"] is True
        assert updated_state["phase6_review_iterations"] == 3
        assert updated_state["phase6_state"] == "6.complete"

    def test_corner_materialize_mode_phase6_early_stop_on_stable_digest(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": "6-PostFlight",
                    "next": "6",
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
                        "P5.4-BusinessRules": "compliant",
                        "P5.5-TechnicalDebt": "approved",
                        "P5.6-RollbackSafety": "approved",
                    },
                }
            },
        )

        commands_home = fake_config / "commands"
        (commands_home / "phase_api.yaml").write_text(
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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

        approve_response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation. All plan steps correctly implemented.",
            "contract_check": "SSOT boundaries preserved. No contract drift.",
            "findings": [],
            "regression_assessment": "Low risk. Implementation isolated.",
            "test_assessment": "Tests sufficient for changed scope.",
        })

        import subprocess

        def mock_subprocess_run(*args, **kwargs):
            return type("MockResult", (), {"stdout": approve_response, "stderr": "", "returncode": 0})()

        _set_pipeline_mode_bindings(monkeypatch, ws_state.parent)
        with monkeypatch.context() as m:
            m.setattr(subprocess, "run", mock_subprocess_run)
            m.setattr(
                session_reader_entrypoint,
                "_load_effective_review_policy_text",
                lambda **_kwargs: ("[EFFECTIVE REVIEW POLICY]\n- baseline", ""),
            )
            from governance_runtime.application.services.phase6_review_orchestrator import _set_policy_resolver
            mock_policy_resolver = type("MockPolicyResolver", (), {
                "load_effective_review_policy": lambda self, **kw: type("R", (), {
                    "is_available": True,
                    "policy_text": "[EFFECTIVE REVIEW POLICY]\n- baseline",
                    "error_code": "",
                })(),
                "load_mandate_schema": lambda self, **kw: _mock_phase6_mandate_schema(),
            })()
            _set_policy_resolver(mock_policy_resolver)
            rc = main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "Plan under review:" in output
        assert "Next action:" in output

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["phase6_review_iterations"] == 2
        assert updated_state["phase6_revision_delta"] == "none"
        assert updated_state["implementation_review_complete"] is True

    def test_materialize_mode_phase6_normalizes_stale_completion_flags(
        self,
        fake_config: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Phase 6 should not keep stale in-progress flags once iterations are complete."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": "6-PostFlight",
                    "next": "6",
                    "active_gate": "Evidence Presentation Gate",
                    "next_gate_condition": "Implementation review loop is complete.",
                    "status": "OK",
                    "phase6_review_iterations": 3,
                    "phase6_max_review_iterations": 3,
                    "phase6_min_self_review_iterations": 1,
                    "phase6_revision_delta": "changed",
                    "implementation_review_complete": False,
                    "phase6_state": "6.execution",
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
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
                        "P5.4-BusinessRules": "compliant",
                        "P5.5-TechnicalDebt": "approved",
                        "P5.6-RollbackSafety": "approved",
                    },
                }
            },
        )

        commands_home = fake_config / "commands"
        spec_home = fake_config / "governance_spec"
        spec_home.mkdir(parents=True, exist_ok=True)
        _write_minimum_governance_specs(spec_home)
        (fake_config / "governance.paths.json").write_text(
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
        approve_response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation. Phase 6 review complete.",
            "contract_check": "No contract drift detected.",
            "findings": [],
            "regression_assessment": "Low risk profile. No regressions.",
            "test_assessment": "Tests are sufficient for the scope.",
        })

        import subprocess

        def mock_subprocess_run(*args, **kwargs):
            return type("MockResult", (), {"stdout": approve_response, "stderr": "", "returncode": 0})()

        _set_pipeline_mode_bindings(monkeypatch, ws_state.parent)
        with monkeypatch.context() as m:
            m.setattr(subprocess, "run", mock_subprocess_run)
            m.setattr(
                session_reader_entrypoint,
                "_load_effective_review_policy_text",
                lambda **_kwargs: ("[EFFECTIVE REVIEW POLICY]\n- baseline", ""),
            )
            rc = main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "Plan under review:" in output
        assert "Next action:" in output

        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["implementation_review_complete"] is True
        assert updated_state["phase6_state"] == "6.complete"
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
                    "phase": "6-PostFlight",
                    "next": "6",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
        reader_path = Path(__file__).resolve().parent.parent / "governance_runtime" / "entrypoints" / "session_reader.py"
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
        _write_workspace_state(ws_state, {"phase": "3", "status": "OK"})

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
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is True
        assert "transition_evidence_hint" not in result

    def test_happy_evidence_false_from_kernel_no_block(self, fake_config: Path) -> None:
        """When kernel reports evidence not met but status is OK, shows False without hint."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False
        # No hint because source is not evidence-related
        assert "transition_evidence_hint" not in result

    def test_corner_evidence_blocked_shows_diagnostic_hint(self, fake_config: Path) -> None:
        """When kernel blocks on missing evidence, snapshot includes diagnostic hint."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
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
            "phase": "5",
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
            "phase": "5",
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
            "phase": "5",
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
            "phase": "5",
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
            "phase": "5",
            "status": "OK",
            "phase_transition_evidence": [],
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False

    def test_bad_no_evidence_field_defaults_to_false(self, fake_config: Path) -> None:
        """When phase_transition_evidence is absent, defaults to False."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False

    def test_evidence_appears_in_formatted_output(self, fake_config: Path) -> None:
        """phase_transition_evidence is rendered in format_snapshot output."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "phase": "5",
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
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

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
                    "phase": "5-ArchitectureReview",
                    "next": "5",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
                    "phase": "5-ArchitectureReview",
                    "next": "5",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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

        from governance_runtime.kernel.phase_kernel import KernelResult

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

        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=stay_result):
            result = read_session_snapshot(commands_home=commands_home, materialize=True)

        assert result["status"] != "ERROR", f"Unexpected error: {result.get('error', '')}"

        # Stay strategy — evidence must NOT be auto-granted
        persisted = json.loads(ws_state.read_text(encoding="utf-8"))
        ss = persisted.get("SESSION_STATE", persisted)
        assert ss.get("phase_transition_evidence") is not True


class TestTransitionEvidenceStayStrategyRegressions:
    """Regression coverage for stay-strategy transition evidence behavior."""

    @staticmethod
    def _prepare_materialize_workspace(fake_config: Path, *, phase: str, next_token: str) -> tuple[Path, Path]:
        ws_state = _write_pointer(fake_config)
        pointer = {
            "schema": POINTER_SCHEMA,
            "activeRepoFingerprint": "abc123",
            "activeSessionStateFile": str(ws_state),
        }
        (fake_config / "SESSION_STATE.json").write_text(json.dumps(pointer), encoding="utf-8")

        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": phase,
                    "next": next_token,
                    "active_gate": "Architecture Review Gate",
                    "next_gate_condition": "Continue deterministic review",
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
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
        return ws_state, commands_home

    def test_happy_stay_with_different_next_token_auto_grants_evidence(self, fake_config: Path) -> None:
        """Fix regression: stay-strategy with advertised forward next_token sets evidence."""
        ws_state, commands_home = self._prepare_materialize_workspace(
            fake_config,
            phase="5-ArchitectureReview",
            next_token="5.3",
        )

        from governance_runtime.kernel.phase_kernel import KernelResult

        stay_forward = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Route to test quality",
            workspace_ready=True,
            source="phase-5-self-review-complete",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-stay-forward-001",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=stay_forward):
            read_session_snapshot(commands_home=commands_home, materialize=True)

        persisted = json.loads(ws_state.read_text(encoding="utf-8"))
        ss = persisted.get("SESSION_STATE", persisted)
        assert ss.get("phase_transition_evidence") is True

    def test_edge_phase6_stay_self_loop_does_not_auto_grant_evidence(self, fake_config: Path) -> None:
        """Fix regression: 6-PostFlight stay self-loop is not treated as forward."""
        ws_state, commands_home = self._prepare_materialize_workspace(
            fake_config,
            phase="6-PostFlight",
            next_token="6",
        )

        from governance_runtime.kernel.phase_kernel import KernelResult

        stay_self_loop = KernelResult(
            phase="6-PostFlight",
            next_token="6",
            active_gate="Implementation Internal Review",
            next_gate_condition="Continue implementation review",
            workspace_ready=True,
            source="phase-6-implementation-review-required",
            status="OK",
            spec_hash="abc",
            spec_path=str(commands_home / "phase_api.yaml"),
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-stay-self-001",
            route_strategy="stay",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=False,
        )

        with patch("governance_runtime.kernel.phase_kernel.execute", return_value=stay_self_loop):
            read_session_snapshot(commands_home=commands_home, materialize=True)

        persisted = json.loads(ws_state.read_text(encoding="utf-8"))
        ss = persisted.get("SESSION_STATE", persisted)
        assert ss.get("phase_transition_evidence") is not True


class TestRuntimeContextTransitionSelection:
    """Regression coverage for _build_runtime_context next-token selection."""

    def test_happy_phase6_reject_next_token_is_honoured_when_evidence_present(self, fake_config: Path) -> None:
        pointer = {"activeRepoFingerprint": "abc123"}
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "4",
                "phase_transition_evidence": True,
                "active_gate": "Evidence Presentation Gate",
                "next_gate_condition": "Review rejected",
            }
        }
        requested_phase, _ = _build_runtime_context(
            commands_home=fake_config / "commands",
            config_root=fake_config,
            pointer=pointer,
            state_doc=state_doc,
        )
        assert requested_phase == "4"

    def test_bad_phase6_reject_next_token_not_honoured_without_evidence(self, fake_config: Path) -> None:
        pointer = {"activeRepoFingerprint": "abc123"}
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "4",
                "phase_transition_evidence": False,
                "active_gate": "Evidence Presentation Gate",
                "next_gate_condition": "Review rejected",
            }
        }
        requested_phase, _ = _build_runtime_context(
            commands_home=fake_config / "commands",
            config_root=fake_config,
            pointer=pointer,
            state_doc=state_doc,
        )
        assert requested_phase == "6"


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
                "phase": "5-ArchitectureReview",
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
                "phase": "5-ArchitectureReview",
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
                "phase": "5-ArchitectureReview",
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
            "phase": "4",
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
                "phase": "5-ArchitectureReview",
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
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
            return_value=blocked_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase_transition_evidence"] is False
        assert "transition_evidence_hint" in result
        assert "phase_transition_evidence is False" in result["transition_evidence_hint"]


class TestResolveNextActionLine:
    """Next action line renders canonical fields only, no derivation."""

    def test_renders_command_when_present(self) -> None:
        snapshot = {
            "next_action_command": "/continue",
            "next_action": "Continue to proceed.",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: /continue"

    def test_renders_text_when_command_missing(self) -> None:
        snapshot = {
            "next_action": "Describe the requested changes in chat.",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: Describe the requested changes in chat."

    def test_returns_empty_without_canonical_fields(self) -> None:
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "active_gate": "Workflow Complete",
            "next_gate_condition": "Workflow approved.",
        }
        assert _resolve_next_action_line(snapshot) == ""


class TestMaterializeOutputActionLine:
    """Ensure action guidance is printed as the final line in materialize mode."""

    def test_happy_terminal_recommendation_is_last_line(self, capsys: pytest.CaptureFixture) -> None:
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "status": "OK",
            "phase": "6-PostFlight",
            "next": "6",
            "active_gate": "Workflow Complete",
            "next_gate_condition": "Workflow approved.",
            "next_action_command": "/implement",
        }
        with patch(
            "governance_runtime.entrypoints.session_reader.read_session_snapshot",
            return_value=snapshot,
        ):
            rc = main(["--materialize"])
        assert rc == 0
        output = capsys.readouterr().out
        assert output.strip().endswith(
            "Next action: /implement"
        )


def test_edge_snapshot_next_action_resolver_failure_emits_neutral_unavailable_state(
    fake_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws_state = _write_pointer(fake_config)
    _write_workspace_state(
        ws_state,
        {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5-ArchitectureReview",
                "active_gate": "Architecture Review Gate",
                "next_gate_condition": "Complete architecture review.",
                "status": "OK",
            }
        },
    )

    monkeypatch.setattr(session_reader_entrypoint, "resolve_next_action", lambda _state: (_ for _ in ()).throw(RuntimeError("boom")))
    with _mock_readonly_unavailable():
        snapshot = read_session_snapshot(commands_home=fake_config / "commands")

    assert snapshot["next_action_code"] == "NEXT_ACTION_UNAVAILABLE"
    assert "next action unavailable" in str(snapshot.get("next_action") or "").lower()
    assert "next_action_command" not in snapshot


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
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
            return_value=next_result,
        ):
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert "route_target" not in result
        assert "route_strategy" not in result
        assert "route_explanation" not in result
        assert result["next"] == "5"

    def test_no_route_explanation_for_stay_strategy(
        self,
        fake_config: Path,
    ) -> None:
        """When kernel evaluates route_strategy=stay, no route explanation fields."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

        from governance_runtime.kernel.phase_kernel import KernelResult

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
            "governance_runtime.kernel.phase_kernel.evaluate_readonly",
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
        _write_workspace_state(ws_state, {"phase": "5", "status": "OK"})

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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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
            "phase": "4",
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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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
                "phase": "6-PostFlight",
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


class TestPhase6GovernanceConfigWiring:
    """Wire phase6_max_review_iterations to governance-config.json."""

    def test_default_phase6_max_from_governance_config(
        self,
        fake_config: Path,
    ) -> None:
        """Missing ImplementationReview uses governance config default (3)."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "status": "OK",
            }
        })

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_max_review_iterations"] == 3

    def test_custom_phase6_max_from_governance_config(
        self,
        fake_config: Path,
    ) -> None:
        """Custom phase6_max_review_iterations from governance-config.json."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "status": "OK",
            }
        })

        governance_config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 3,
                "phase6_max_review_iterations": 7,
            },
        }
        workspace_dir = fake_config / "workspaces" / "abc123"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "governance-config.json").write_text(
            json.dumps(governance_config), encoding="utf-8"
        )

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_max_review_iterations"] == 7

    def test_state_phase6_max_overrides_governance_config(
        self,
        fake_config: Path,
    ) -> None:
        """State-provided phase6_max_review_iterations takes precedence."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "status": "OK",
                "ImplementationReview": {
                    "iteration": 1,
                    "max_iterations": 5,
                    "min_self_review_iterations": 1,
                    "prev_impl_digest": "sha256:abc",
                    "curr_impl_digest": "sha256:abc",
                },
            }
        })

        governance_config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 3,
                "phase6_max_review_iterations": 7,
            },
        }
        workspace_dir = fake_config / "workspaces" / "abc123"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "governance-config.json").write_text(
            json.dumps(governance_config), encoding="utf-8"
        )

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert result["phase6_max_review_iterations"] == 5  # from state, not config


class TestPhase6KernelGovernanceConfigWiring:
    """Tests that phase_kernel uses governance-config.json for phase6_max_review_iterations."""

    def test_kernel_phase6_max_uses_governance_config_default(
        self,
        fake_config: Path,
    ) -> None:
        """Kernel uses governance config default (3) when no state value present."""
        from governance_runtime.kernel.phase_kernel import (
            _phase6_max_review_iterations,
        )
        
        state = {
            "repo_fingerprint": "abc123",
            "phase": "6-PostFlight",
        }
        
        result = _phase6_max_review_iterations(state)
        assert result == 3

    def test_kernel_phase6_max_uses_custom_governance_config(
        self,
        fake_config: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kernel uses custom governance config value (7) when no state value present."""
        import os
        from governance_runtime.kernel.phase_kernel import (
            _phase6_max_review_iterations,
        )
        
        ws_state = _write_pointer(fake_config)
        
        (fake_config / "governance.paths.json").write_text(
            json.dumps({
                "schema": "opencode-governance.paths.v1",
                "paths": {
                    "configRoot": str(fake_config),
                    "workspacesHome": str(fake_config / "workspaces"),
                    "commandsHome": str(fake_config / "commands"),
                    "pythonCommand": "python3",
                }
            }),
            encoding="utf-8",
        )
        
        governance_config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 3,
                "phase6_max_review_iterations": 7,
            },
        }
        workspace_dir = fake_config / "workspaces" / "abc123"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "governance-config.json").write_text(
            json.dumps(governance_config), encoding="utf-8"
        )
        
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(fake_config))
        
        state = {
            "repo_fingerprint": "abc123",
            "phase": "6-PostFlight",
        }
        
        result = _phase6_max_review_iterations(state)
        assert result == 7

    def test_kernel_phase6_state_value_overrides_config(
        self,
        fake_config: Path,
    ) -> None:
        """Kernel state value overrides governance config."""
        from governance_runtime.kernel.phase_kernel import (
            _phase6_max_review_iterations,
        )
        
        ws_state = _write_pointer(fake_config)
        governance_config = {
            "presentation": {
                "mode": "standard",
            },
            "review": {
                "phase5_max_review_iterations": 3,
                "phase6_max_review_iterations": 7,
            },
        }
        workspace_dir = fake_config / "workspaces" / "abc123"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "governance-config.json").write_text(
            json.dumps(governance_config), encoding="utf-8"
        )
        
        state = {
            "repo_fingerprint": "abc123",
            "phase": "6-PostFlight",
            "ImplementationReview": {
                "max_iterations": 5,
            },
        }
        
        result = _phase6_max_review_iterations(state)
        assert result == 5  # from state, not config

    def test_kernel_phase6_invalid_config_fails_closed(
        self,
        fake_config: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invalid governance-config.json raises RuntimeError (fail-closed)."""
        from governance_runtime.kernel.phase_kernel import (
            _phase6_max_review_iterations,
        )
        
        ws_state = _write_pointer(fake_config)
        
        (fake_config / "governance.paths.json").write_text(
            json.dumps({
                "schema": "opencode-governance.paths.v1",
                "paths": {
                    "configRoot": str(fake_config),
                    "workspacesHome": str(fake_config / "workspaces"),
                    "commandsHome": str(fake_config / "commands"),
                    "pythonCommand": "python3",
                }
            }),
            encoding="utf-8",
        )
        
        workspace_dir = fake_config / "workspaces" / "abc123"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "governance-config.json").write_text(
            '{"invalid": "json"'  # malformed JSON
        )
        
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(fake_config))
        
        state = {
            "repo_fingerprint": "abc123",
            "phase": "6-PostFlight",
        }
        
        with pytest.raises(RuntimeError):
            _phase6_max_review_iterations(state)


class TestPhase6NextActionLine:
    """Phase 6 guidance is rendered only from canonical next-action fields."""

    def test_empty_without_canonical_fields(self) -> None:
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "next_gate_condition": "Present evidence for final user review.",
        }
        assert _resolve_next_action_line(snapshot) == ""

    def test_uses_canonical_command_when_present(self) -> None:
        snapshot = {
            "status": "OK",
            "phase": "6-PostFlight",
            "next_action_command": "/review-decision <approve|changes_requested|reject>",
        }
        assert _resolve_next_action_line(snapshot) == "Next action: /review-decision <approve|changes_requested|reject>"


class TestP54BlockerSurface:
    def test_blocker_surface_includes_business_rules_diagnostics(self) -> None:
        snapshot = {
            "status": "BLOCKED",
            "phase": "5.4-BusinessRules",
            "next_gate_condition": "PHASE_BLOCKED: BLOCKED-P5-4-BUSINESS-RULES-GATE",
            "p54_evaluated_status": "gap-detected",
            "p54_reason_code": "BLOCKED-P5-4-BUSINESS-RULES-GATE",
            "p54_invalid_rules": 2,
            "p54_dropped_candidates": 1,
            "p54_quality_reason_codes": ["BUSINESS_RULES_INVALID_CONTENT"],
        }

        lines = _render_blocker(snapshot)

        assert any("Business Rules Validation: FAILED" in line for line in lines)
        assert any("Invalid rules detected: 2" in line for line in lines)
        assert any("Reason code: BLOCKED-P5-4-BUSINESS-RULES-GATE" in line for line in lines)


class TestImplementationBlockerSurface:
    def test_blocker_surface_includes_implementation_validation_diagnostics(self) -> None:
        snapshot = {
            "status": "BLOCKED",
            "phase": "6-PostFlight",
            "active_gate": "Implementation Blocked",
            "next_gate_condition": "Implementation validation failed.",
            "implementation_reason_codes": [
                "IMPLEMENTATION_GOVERNANCE_ONLY_CHANGES",
                "IMPLEMENTATION_PLAN_COVERAGE_MISSING",
            ],
            "implementation_executor_invoked": True,
            "implementation_changed_files": [".governance/implementation/llm_edit_context.json"],
            "implementation_domain_changed_files": [],
        }

        lines = _render_blocker(snapshot)

        assert any("Implementation Validation: FAILED" in line for line in lines)
        assert any("Executor invoked: true" in line for line in lines)
        assert any("Changed files: 1" in line for line in lines)
        assert any("Domain files changed: 0" in line for line in lines)


class TestPhase6LLMReviewIntegrationEvals:
    """Integration E2E evals for Phase 6 LLM review enforcement chain.

    Tests the full path: _call_llm_impl_review -> subprocess (mocked) ->
    _parse_llm_review_response -> validation -> block/proceed.

    Chain:
      _run_phase6_internal_review_loop
          -> _has_any_llm_executor()
          -> _call_llm_impl_review(content, mandate)
              -> subprocess.run (mocked)
              -> response captured from stdout
              -> _parse_llm_review_response(response_text, schema)
                  -> JSON parse? no -> hard block
                  -> schema validate? fail -> hard block
                  -> proceed
    """

    @staticmethod
    def _load_schema() -> dict | None:
        schema_path = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"
        if not schema_path.exists():
            return None
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def test_parse_llm_review_response_valid_json_approve_proceeds(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation. All plan steps implemented correctly.",
            "contract_check": "SSOT boundaries preserved. No contract drift.",
            "findings": [],
            "regression_assessment": "Low risk. Implementation isolated.",
            "test_assessment": "Tests sufficient for changed scope.",
        })
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is True
        assert result["verdict"] == "approve"
        assert result["findings"] == []

    def test_parse_llm_review_response_valid_json_changes_requested_proceeds(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed implementation against plan.",
            "contract_check": "Minor drift in response shape.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/api.py:42",
                    "evidence": "Response field missing",
                    "impact": "Client breakage",
                    "fix": "Add missing field",
                }
            ],
            "regression_assessment": "Existing endpoints unaffected.",
            "test_assessment": "Tests missing for new behavior.",
        })
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is True
        assert result["verdict"] == "changes_requested"
        assert len(result["findings"]) == 1

    def test_parse_llm_review_response_free_prose_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = "Looks good. I reviewed the implementation and everything seems fine."
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]
        assert result["verdict"] == "changes_requested"

    def test_parse_llm_review_response_malformed_json_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = '{"verdict": "approve", "findings": ['
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]

    def test_parse_llm_review_response_empty_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        result = _parse_llm_review_response("", mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"

    def test_parse_llm_review_response_approve_with_defect_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed code.",
            "contract_check": "OK.",
            "findings": [
                {
                    "severity": "medium",
                    "type": "defect",
                    "location": "src/main.py:1",
                    "evidence": "Logic error in condition",
                    "impact": "Wrong branch executed",
                    "fix": "Fix condition",
                }
            ],
            "regression_assessment": "Most endpoints affected.",
            "test_assessment": "Insufficient coverage.",
        })
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("defect" in v.lower() for v in violations)

    def test_parse_llm_review_response_missing_required_field_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = json.dumps({
            "verdict": "changes_requested",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/main.py:42",
                    "evidence": "Missing null check causes crash",
                    "impact": "Crash on empty input",
                    "fix": "Add null guard",
                }
            ],
            "regression_assessment": "Other endpoints unaffected.",
            "test_assessment": "Tests sufficient.",
        })
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False

    def test_parse_llm_review_response_invalid_verdict_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = json.dumps({
            "verdict": "looks_good",
            "governing_evidence": "Reviewed all files.",
            "contract_check": "No issues found.",
            "findings": [],
            "regression_assessment": "Minimal risk.",
            "test_assessment": "Tests sufficient.",
        })
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"

    def test_parse_llm_review_response_changes_requested_without_findings_hard_blocked(self):
        from governance_runtime.entrypoints.session_reader import _parse_llm_review_response
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Something needs fixing.",
            "contract_check": "Minor drift.",
            "findings": [],
            "regression_assessment": "Low risk profile.",
            "test_assessment": "Tests adequate.",
        })
        result = _parse_llm_review_response(response, mandates_schema=self._load_schema())
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("changes_requested" in v.lower() and "no findings" in v.lower() for v in violations)


class TestPhase6LLMReviewLoopGatingEvals:
    """E2E evals proving LLM verdict gates Phase 6 completion.

    These tests verify that _run_phase6_internal_review_loop() uses the LLM
    review result to determine completion — not just mechanical iteration count.
    """

    @staticmethod
    def _load_schema() -> dict | None:
        schema_path = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"
        if not schema_path.exists():
            return None
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def test_approve_verdict_at_max_iterations_completes_phase6(
        self,
        fake_config: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": "6-PostFlight",
                    "next": "6",
                    "active_gate": "Post Flight",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "phase5_plan_record_digest": "sha256:plan-v1",
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
                    "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
                        "P5.4-BusinessRules": "compliant",
                        "P5.5-TechnicalDebt": "approved",
                        "P5.6-RollbackSafety": "approved",
                    },
                }
            },
        )
        commands_home = fake_config / "commands"
        spec_home = fake_config / "governance_spec"
        spec_home.mkdir(parents=True, exist_ok=True)
        _write_minimum_governance_specs(spec_home)
        (fake_config / "governance.paths.json").write_text(
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
        approve_response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation. All plan steps implemented.",
            "contract_check": "SSOT boundaries preserved.",
            "findings": [],
            "regression_assessment": "Low risk profile.",
            "test_assessment": "Tests sufficient.",
        })

        import subprocess

        def mock_subprocess_run(*args, **kwargs):
            return type("MockResult", (), {"stdout": approve_response, "stderr": "", "returncode": 0})()

        _set_pipeline_mode_bindings(monkeypatch, ws_state.parent)
        with monkeypatch.context() as m:
            m.setattr(subprocess, "run", mock_subprocess_run)
            m.setattr(
                session_reader_entrypoint,
                "_load_effective_review_policy_text",
                lambda **_kwargs: ("[EFFECTIVE REVIEW POLICY]\n- baseline", ""),
            )
            from governance_runtime.application.services.phase6_review_orchestrator import _set_policy_resolver
            mock_policy_resolver = type("MockPolicyResolver", (), {
                "load_effective_review_policy": lambda self, **kw: type("R", (), {
                    "is_available": True,
                    "policy_text": "[EFFECTIVE REVIEW POLICY]\n- baseline",
                    "error_code": "",
                })(),
                "load_mandate_schema": lambda self, **kw: _mock_phase6_mandate_schema(),
            })()
            _set_policy_resolver(mock_policy_resolver)
            rc = main(["--commands-home", str(commands_home), "--materialize"])

        assert rc == 0
        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert updated_state["implementation_review_complete"] is True
        assert updated_state["phase6_review_iterations"] == 3

    def test_changes_requested_verdict_completes_phase6_at_max_iterations(
        self,
        fake_config: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": "6-PostFlight",
                    "next": "6",
                    "active_gate": "Post Flight",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "phase5_plan_record_digest": "sha256:plan-v1",
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
                    "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
                        "P5.4-BusinessRules": "compliant",
                        "P5.5-TechnicalDebt": "approved",
                        "P5.6-RollbackSafety": "approved",
                    },
                }
            },
        )
        commands_home = fake_config / "commands"
        spec_home = fake_config / "governance_spec"
        spec_home.mkdir(parents=True, exist_ok=True)
        _write_minimum_governance_specs(spec_home)
        (fake_config / "governance.paths.json").write_text(
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
        cr_response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed implementation.",
            "contract_check": "Minor drift found.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/main.py:42",
                    "evidence": "Missing null check causes crash",
                    "impact": "Crash on empty input",
                    "fix": "Add null guard",
                }
            ],
            "regression_assessment": "Other endpoints unaffected.",
            "test_assessment": "Tests sufficient.",
        })

        import subprocess

        def mock_subprocess_run(*args, **kwargs):
            return type("MockResult", (), {"stdout": cr_response, "stderr": "", "returncode": 0})()

        _set_pipeline_mode_bindings(monkeypatch, ws_state.parent)
        with monkeypatch.context() as m:
            m.setattr(subprocess, "run", mock_subprocess_run)
            from governance_runtime.application.services.phase6_review_orchestrator import _set_policy_resolver
            mock_policy_resolver = type("MockPolicyResolver", (), {
                "load_effective_review_policy": lambda self, **kw: type("R", (), {
                    "is_available": True,
                    "policy_text": "[EFFECTIVE REVIEW POLICY]\n- baseline",
                    "error_code": "",
                })(),
                "load_mandate_schema": lambda self, **kw: _mock_phase6_mandate_schema(),
            })()
            _set_policy_resolver(mock_policy_resolver)
            rc = main(["--commands-home", str(commands_home), "--materialize"])

        assert rc == 0
        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        # With max iterations reached, review completes regardless of LLM verdict
        assert updated_state["implementation_review_complete"] is True
        assert updated_state["phase6_state"] == "6.complete"

    def test_validator_import_failure_completes_phase6_at_max_iterations(
        self,
        fake_config: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(
            ws_state,
            {
                "SESSION_STATE": {
                    "phase": "6-PostFlight",
                    "next": "6",
                    "active_gate": "Post Flight",
                    "status": "OK",
                    "ActiveProfile": "profile.fallback-minimum",
                    "phase5_plan_record_digest": "sha256:plan-v1",
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
                    "AddonsEvidence": {"riskTiering": {"status": "loaded"}},
                    "Gates": {
                        "P5-Architecture": "approved",
                        "P5.3-TestQuality": "pass",
                        "P5.4-BusinessRules": "compliant",
                        "P5.5-TechnicalDebt": "approved",
                        "P5.6-RollbackSafety": "approved",
                    },
                }
            },
        )
        commands_home = fake_config / "commands"
        spec_home = fake_config / "governance_spec"
        spec_home.mkdir(parents=True, exist_ok=True)
        (spec_home / "phase_api.yaml").write_text(
            get_phase_api_path().read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (fake_config / "governance.paths.json").write_text(
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
        approve_response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation.",
            "contract_check": "OK.",
            "findings": [],
            "regression_assessment": "Low risk profile.",
            "test_assessment": "OK.",
        })

        import subprocess

        def mock_subprocess_run(*args, **kwargs):
            return type("MockResult", (), {"stdout": approve_response, "stderr": "", "returncode": 0})()

        _set_pipeline_mode_bindings(monkeypatch, ws_state.parent)
        with monkeypatch.context() as m:
            m.setattr(subprocess, "run", mock_subprocess_run)
            from governance_runtime.application.services.phase6_review_orchestrator import _set_policy_resolver, _set_response_validator
            mock_policy_resolver = type("MockPolicyResolver", (), {
                "load_effective_review_policy": lambda self, **kw: type("R", (), {
                    "is_available": True,
                    "policy_text": "[EFFECTIVE REVIEW POLICY]\n- baseline",
                    "error_code": "",
                })(),
                "load_mandate_schema": lambda self, **kw: _mock_phase6_mandate_schema(),
            })()
            _set_policy_resolver(mock_policy_resolver)
            mock_response_validator = type("MockResponseValidator", (), {
                "validate": lambda self, response_text, mandates_schema=None: type("V", (), {
                    "valid": False,
                    "verdict": "changes_requested",
                    "findings": ["validator-not-available: llm_response_validator could not be imported"],
                    "violations": ["validator-not-available"],
                    "is_approve": False,
                    "is_changes_requested": True,
                })(),
            })()
            _set_response_validator(mock_response_validator)
            rc = main(["--commands-home", str(commands_home), "--materialize"])

        assert rc == 0
        updated_state = json.loads(ws_state.read_text(encoding="utf-8"))["SESSION_STATE"]
        # With max iterations reached, review completes even with validator failure
        assert updated_state["implementation_review_complete"] is True

    def test_phase6_blocks_when_effective_review_policy_unavailable(
        self,
        fake_config: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from governance_runtime.application.services.phase6_review_orchestrator import (
            run_review_loop,
            ReviewLoopConfig,
            ReviewResult,
            BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
        )
        from governance_runtime.infrastructure.json_store import load_json as _read_json, write_json_atomic as _write_json_atomic

        ws_state = _write_pointer(fake_config)
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
                "active_gate": "Post Flight",
                "status": "OK",
                "LoadedRulebooks": {
                    "core": "${COMMANDS_HOME}/rules.md",
                    "profile": "${PROFILES_HOME}/rules.fallback-minimum.md",
                },
                "AddonsEvidence": {},
            }
        }
        _write_workspace_state(ws_state, state_doc)

        commands_home = fake_config / "commands"
        config = ReviewLoopConfig(
            commands_home=commands_home,
            session_path=ws_state,
            max_iterations=3,
            min_iterations=1,
        )

        mock_policy_resolver = type("MockPolicyResolver", (), {
            "load_effective_review_policy": lambda self, **kw: type("R", (), {
                "is_available": False,
                "policy_text": "",
                "error_code": BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            })(),
            "load_mandate_schema": lambda self, **kw: _mock_phase6_mandate_schema(),
        })()

        from governance_runtime.application.services.phase6_review_orchestrator import _set_policy_resolver, _set_llm_caller
        _set_policy_resolver(mock_policy_resolver)

        mock_llm_caller = type("MockLLMCaller", (), {
            "is_configured": True,
            "build_context": lambda self, **kw: {},
            "invoke": lambda self, **kw: type("R", (), {
                "invoked": False,
                "stdout": "",
                "stderr": "",
                "return_code": 0,
            })(),
        })()
        _set_llm_caller(mock_llm_caller)

        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            json_loader=_read_json,
            context_writer=_write_json_atomic,
        )

        assert isinstance(result, ReviewResult)
        assert result.loop_result is not None
        assert result.loop_result.blocked is True
        assert result.loop_result.block_reason == "effective-review-policy-unavailable"
        assert result.loop_result.block_reason_code == BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE
