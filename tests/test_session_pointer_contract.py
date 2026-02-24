from __future__ import annotations

from governance.infrastructure.session_pointer import is_valid_pointer, parse_pointer_payload


def test_parse_pointer_payload_rejects_missing_required_fields() -> None:
    payload = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
    }
    assert parse_pointer_payload(payload) == {}


def test_parse_pointer_payload_rejects_relative_mismatch() -> None:
    payload = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
        "activeSessionStateFile": "/tmp/workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
        "activeSessionStateRelativePath": "workspaces/ffffffffffffffffffffffff/SESSION_STATE.json",
    }
    assert parse_pointer_payload(payload) == {}


def test_is_valid_pointer_requires_absolute_and_consistent_paths() -> None:
    payload = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
        "activeSessionStateFile": "/tmp/workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
        "activeSessionStateRelativePath": "workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
    }
    assert is_valid_pointer(payload) is True
