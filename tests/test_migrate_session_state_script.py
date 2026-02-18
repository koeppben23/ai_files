from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_session_state.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run migration script and capture deterministic output."""

    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(SCRIPT.parents[1]),
    )


def _legacy_document() -> dict[str, object]:
    """Build minimal legacy SESSION_STATE payload for migration tests."""

    return {
        "SESSION_STATE": {
            "session_state_version": 1,
            "ruleset_hash": "hash-a",
            "RepoModel": {"components": ["engine"]},
            "FastPath": True,
            "FastPathReason": "legacy reason",
        }
    }


@pytest.mark.governance
def test_script_migrates_legacy_file_and_creates_backup(tmp_path: Path):
    """Script should canonicalize legacy aliases and preserve first-write backup."""

    workspaces = tmp_path / "workspaces"
    target = workspaces / "repo-a" / "SESSION_STATE.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_legacy_document()), encoding="utf-8")

    result = _run(["--workspace", "repo-a", "--workspaces-root", str(workspaces)])
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "ok"
    assert payload["changed"] is True
    backup = target.with_suffix(".json.backup")
    assert backup.exists()

    migrated = json.loads(target.read_text(encoding="utf-8"))
    state = migrated["SESSION_STATE"]
    assert "RepoModel" not in state
    assert "FastPath" not in state
    assert "FastPathReason" not in state
    assert "RepoMapDigest" in state
    assert "FastPathEvaluation" in state


@pytest.mark.governance
def test_script_is_idempotent_after_first_migration(tmp_path: Path):
    """Second migration run should keep payload stable and not rewrite backup."""

    workspaces = tmp_path / "workspaces"
    target = workspaces / "repo-b" / "SESSION_STATE.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_legacy_document()), encoding="utf-8")

    first = _run(["--workspace", "repo-b", "--workspaces-root", str(workspaces)])
    assert first.returncode == 0
    backup = target.with_suffix(".json.backup")
    first_backup = backup.read_text(encoding="utf-8")

    second = _run(["--workspace", "repo-b", "--workspaces-root", str(workspaces)])
    second_payload = json.loads(second.stdout)
    assert second.returncode == 0
    assert second_payload["changed"] is False
    assert backup.read_text(encoding="utf-8") == first_backup


@pytest.mark.governance
def test_script_returns_blocked_for_missing_file(tmp_path: Path):
    """Missing target file should return blocked exit code 2."""

    result = _run(["--workspace", "missing", "--workspaces-root", str(tmp_path / "workspaces")])
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "blocked"


@pytest.mark.governance
def test_script_returns_blocked_for_malformed_json(tmp_path: Path):
    """Malformed payload should fail closed with blocked exit code."""

    target = tmp_path / "workspaces" / "repo-c" / "SESSION_STATE.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not-json", encoding="utf-8")

    result = _run(["--file", str(target)])
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "blocked"
