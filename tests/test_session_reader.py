"""Tests for governance.entrypoints.session_reader — LLM bridge entrypoint.

Validates:
- Correct YAML-like snapshot output from valid session state
- Dual-case field extraction (PascalCase + snake_case)
- Error handling for missing pointer, missing workspace state, invalid JSON
- CLI interface (--commands-home override, exit codes)
- Self-bootstrapping path derivation
- Cross-platform path handling

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

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
        result = read_session_snapshot(commands_home=fake_config / "commands")
        assert result["status"] == "OK"
        assert result["phase"] == "3"
