from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.infrastructure.session_pointer import (
    CANONICAL_POINTER_SCHEMA,
    build_pointer_payload,
    is_session_pointer_document,
    parse_session_pointer_document,
    resolve_active_session_state_path,
)


def test_happy_parse_session_pointer_document_normalizes_canonical_pointer(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    session_path = config_root / "workspaces" / "a1b2c3d4e5f6a1b2c3d4e5f6" / "SESSION_STATE.json"
    payload = build_pointer_payload(
        repo_fingerprint="a1b2c3d4e5f6a1b2c3d4e5f6",
        session_state_file=session_path,
        config_root=config_root,
    )

    parsed = parse_session_pointer_document(payload)
    resolved = resolve_active_session_state_path(parsed, config_root=config_root)

    assert is_session_pointer_document(payload) is True
    assert parsed["schema"] == CANONICAL_POINTER_SCHEMA
    assert parsed["activeRepoFingerprint"] == "a1b2c3d4e5f6a1b2c3d4e5f6"
    assert parsed["activeSessionStateRelativePath"] == "workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json"
    assert resolved == session_path.resolve()


def test_bad_parse_session_pointer_document_rejects_relative_traversal(tmp_path: Path) -> None:
    config_root = tmp_path / "config"

    with pytest.raises(ValueError, match="activeSessionStateRelativePath"):
        pointer = {
            "schema": CANONICAL_POINTER_SCHEMA,
            "activeSessionStateRelativePath": "../outside/SESSION_STATE.json",
        }
        resolve_active_session_state_path(pointer, config_root=config_root)


def test_corner_parse_session_pointer_document_accepts_legacy_pointer_keys(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    session_path = config_root / "workspaces" / "a1b2c3d4e5f6a1b2c3d4e5f6" / "SESSION_STATE.json"
    payload = {
        "schema": "active-session-pointer.v1",
        "repo_fingerprint": "A1B2C3D4E5F6A1B2C3D4E5F6",
        "active_session_state_file": str(session_path),
        "active_session_state_relative_path": "workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
    }

    parsed = parse_session_pointer_document(payload)

    assert parsed == {
        "schema": CANONICAL_POINTER_SCHEMA,
        "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
        "activeSessionStateFile": session_path.resolve().as_posix(),
        "activeSessionStateRelativePath": "workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
    }


def test_edge_parse_session_pointer_document_resolves_relative_only_pointer(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    payload = {
        "schema": CANONICAL_POINTER_SCHEMA,
        "activeSessionStateRelativePath": "workspaces/abc123/SESSION_STATE.json",
    }

    parsed = parse_session_pointer_document(payload)
    resolved = resolve_active_session_state_path(parsed, config_root=config_root)

    assert "activeRepoFingerprint" not in parsed
    assert resolved == (config_root / "workspaces" / "abc123" / "SESSION_STATE.json").resolve()
