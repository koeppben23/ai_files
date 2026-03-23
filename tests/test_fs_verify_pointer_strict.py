from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.entrypoints.io.fs_verify import verify_pointer


def test_verify_pointer_requires_required_session_fields(tmp_path: Path) -> None:
    pointer = tmp_path / "SESSION_STATE.json"
    pointer.write_text(
        json.dumps(
            {
                "schema": "opencode-session-pointer.v1",
                "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
            }
        ),
        encoding="utf-8",
    )

    ok, reason = verify_pointer(pointer, "a1b2c3d4e5f6a1b2c3d4e5f6")
    assert ok is False
    assert reason and "activeSessionStateFile" in reason


def test_verify_pointer_rejects_relative_path_mismatch(tmp_path: Path) -> None:
    pointer = tmp_path / "SESSION_STATE.json"
    pointer.write_text(
        json.dumps(
            {
                "schema": "opencode-session-pointer.v1",
                "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
                "activeSessionStateFile": "/mock/workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
                "activeSessionStateRelativePath": "workspaces/ffffffffffffffffffffffff/SESSION_STATE.json",
            }
        ),
        encoding="utf-8",
    )

    ok, reason = verify_pointer(pointer, "a1b2c3d4e5f6a1b2c3d4e5f6")
    assert ok is False
    assert reason and "Relative path mismatch" in reason
