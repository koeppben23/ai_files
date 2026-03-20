from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from governance_runtime.entrypoints import session_reader
from governance_runtime.infrastructure import session_pointer as pointer_module


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _mock_readonly_unavailable():
    return patch(
        "governance_runtime.kernel.phase_kernel.evaluate_readonly",
        side_effect=RuntimeError("kernel not available in test"),
    )


def test_happy_session_reader_uses_canonical_pointer_parser(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    workspace = config_root / "workspaces" / "abc123"
    commands_home.mkdir(parents=True)
    _write_json(workspace / "SESSION_STATE.json", {"Phase": "4", "status": "OK"})
    _write_json(
        config_root / "SESSION_STATE.json",
        {
            "schema": session_reader.POINTER_SCHEMA,
            "activeSessionStateRelativePath": "workspaces/abc123/SESSION_STATE.json",
        },
    )

    calls = {"parse": 0, "resolve": 0}
    original_parse = pointer_module.parse_session_pointer_document
    original_resolve = pointer_module.resolve_active_session_state_path

    def wrapped_parse(payload: object) -> dict[str, str]:
        calls["parse"] += 1
        return original_parse(payload)

    def wrapped_resolve(pointer: dict[str, str], *, config_root: Path) -> Path:
        calls["resolve"] += 1
        return original_resolve(pointer, config_root=config_root)

    monkeypatch.setattr(session_reader, "parse_session_pointer_document", wrapped_parse)
    monkeypatch.setattr(session_reader, "resolve_active_session_state_path", wrapped_resolve)

    with _mock_readonly_unavailable():
        result = session_reader.read_session_snapshot(commands_home=commands_home)

    assert result["status"] == "OK"
    assert result["phase"] == "4"
    assert calls == {"parse": 1, "resolve": 1}


def test_bad_session_reader_surfaces_canonical_parser_errors(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    commands_home.mkdir(parents=True)
    _write_json(config_root / "SESSION_STATE.json", {"schema": "bogus.v99"})

    result = session_reader.read_session_snapshot(commands_home=commands_home)

    assert result["status"] == "ERROR"
    assert "Unknown pointer schema: bogus.v99" in result["error"]


def test_corner_session_reader_prefers_canonical_parser_output_over_raw_keys(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    workspace = config_root / "workspaces" / "abc123"
    commands_home.mkdir(parents=True)
    _write_json(workspace / "SESSION_STATE.json", {"Phase": "2", "status": "OK"})
    _write_json(
        config_root / "SESSION_STATE.json",
        {
            "schema": session_reader.POINTER_SCHEMA,
            "activeSessionStateFile": str(tmp_path / "wrong" / "SESSION_STATE.json"),
            "activeSessionStateRelativePath": "workspaces/abc123/SESSION_STATE.json",
        },
    )

    parsed_pointer = {
        "schema": session_reader.POINTER_SCHEMA,
        "activeRepoFingerprint": "abc123",
        "activeSessionStateRelativePath": "workspaces/abc123/SESSION_STATE.json",
    }

    monkeypatch.setattr(session_reader, "parse_session_pointer_document", lambda payload: dict(parsed_pointer))
    monkeypatch.setattr(
        session_reader,
        "resolve_active_session_state_path",
        lambda pointer, *, config_root: (config_root / pointer["activeSessionStateRelativePath"]).resolve(),
    )

    with _mock_readonly_unavailable():
        result = session_reader.read_session_snapshot(commands_home=commands_home)

    assert result["status"] == "OK"
    assert result["phase"] == "2"


def test_edge_session_reader_accepts_relative_only_pointer_via_canonical_parser(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    commands_home = config_root / "commands"
    workspace = config_root / "workspaces" / "abc123"
    commands_home.mkdir(parents=True)
    _write_json(workspace / "SESSION_STATE.json", {"Phase": "3", "status": "OK"})
    _write_json(
        config_root / "SESSION_STATE.json",
        {
            "schema": session_reader.POINTER_SCHEMA,
            "activeSessionStateRelativePath": "workspaces/abc123/SESSION_STATE.json",
        },
    )

    with _mock_readonly_unavailable():
        result = session_reader.read_session_snapshot(commands_home=commands_home)

    assert result["status"] == "OK"
    assert result["phase"] == "3"
