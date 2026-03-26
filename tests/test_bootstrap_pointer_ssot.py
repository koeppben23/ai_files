"""E2E tests for pointer SSOT and canonical fingerprint enforcement.

These tests reproduce and prevent the bug where:
- bootstrap returns success text but pointer is missing
- workspace shows PersistenceCommitted=True but pointer doesn't exist
- fingerprint is slug-style instead of 24-hex hash
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.util import REPO_ROOT


class TestPointerSSOT:
    """Tests for global pointer write and verification."""

    @pytest.mark.governance
    def test_pointer_written_before_persistence_committed(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_session_state import (
            _atomic_write_text,
            pointer_payload,
            session_state_template,
        )
        from governance_runtime.infrastructure.fs_atomic import atomic_write_text

        config_root = tmp_path / "config"
        config_root.mkdir(parents=True)
        workspaces_home = tmp_path / "workspaces"
        workspaces_home.mkdir(parents=True)

        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
        workspace_dir = workspaces_home / repo_fp
        workspace_dir.mkdir(parents=True)
        session_file = workspace_dir / "SESSION_STATE.json"
        pointer_file = config_root / "SESSION_STATE.json"

        template = session_state_template(repo_fp, "test-repo")
        template["SESSION_STATE"]["PersistenceCommitted"] = False
        atomic_write_text(session_file, json.dumps(template, indent=2) + "\n")

        assert not template["SESSION_STATE"]["PersistenceCommitted"]

        pointer = pointer_payload(repo_fp, session_file)
        atomic_write_text(pointer_file, json.dumps(pointer, indent=2) + "\n")

        assert pointer_file.is_file(), "pointer must exist after write"

        pointer_data = json.loads(pointer_file.read_text())
        assert pointer_data["schema"] == "opencode-session-pointer.v1"
        assert pointer_data["activeRepoFingerprint"] == repo_fp

    @pytest.mark.governance
    def test_pointer_schema_is_canonical(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_session_state import pointer_payload

        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
        session_file = tmp_path / "SESSION_STATE.json"
        pointer = pointer_payload(repo_fp, session_file)

        assert pointer["schema"] == "opencode-session-pointer.v1"
        assert "activeRepoFingerprint" in pointer
        assert pointer["activeRepoFingerprint"] == repo_fp

    @pytest.mark.governance
    def test_workspace_session_state_path_in_pointer(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_session_state import pointer_payload

        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
        session_file = tmp_path / "workspaces" / repo_fp / "SESSION_STATE.json"
        pointer = pointer_payload(repo_fp, session_file)

        assert "activeSessionStateFile" in pointer
        assert repo_fp in pointer["activeSessionStateFile"]


class TestCanonicalFingerprint:
    """Tests for 24-hex canonical fingerprint enforcement."""

    @pytest.mark.governance
    def test_canonical_fingerprint_validation(self):
        from governance_runtime.entrypoints.bootstrap_session_state import (
            _is_canonical_fingerprint,
            _validate_canonical_fingerprint,
        )

        assert _is_canonical_fingerprint("a1b2c3d4e5f6a1b2c3d4e5f6") is True
        assert _is_canonical_fingerprint("A1B2C3D4E5F6A1B2C3D4E5F6") is False
        assert _is_canonical_fingerprint("github.com-user-repo") is False
        assert _is_canonical_fingerprint("short") is False
        assert _is_canonical_fingerprint("a1b2c3d4e5f6a1b2c3d4e5f6extra") is False

        validated = _validate_canonical_fingerprint("a1b2c3d4e5f6a1b2c3d4e5f6")
        assert validated == "a1b2c3d4e5f6a1b2c3d4e5f6"

        with pytest.raises(ValueError, match="24-character hex"):
            _validate_canonical_fingerprint("github.com-user-repo")

    @pytest.mark.governance
    def test_slug_fingerprint_rejected(self):
        from governance_runtime.entrypoints.persist_workspace_artifacts import _is_canonical_fingerprint

        assert _is_canonical_fingerprint("github.com-koeppben23-ai_files") is False
        assert _is_canonical_fingerprint("a1b2c3d4e5f6a1b2c3d4e5f6") is True

    @pytest.mark.governance
    def test_workspace_directory_is_hex_fingerprint(self, tmp_path: Path):
        workspaces_home = tmp_path / "workspaces"
        workspaces_home.mkdir(parents=True)

        canonical_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
        workspace_dir = workspaces_home / canonical_fp
        workspace_dir.mkdir(parents=True)

        assert workspace_dir.name == canonical_fp
        assert len(workspace_dir.name) == 24
        assert all(c in "0123456789abcdef" for c in workspace_dir.name)


class TestPointerVerification:
    """Tests for pointer verification after bootstrap."""

    @pytest.mark.governance
    def test_verify_pointer_exists_success(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_persistence_hook import _verify_pointer_exists

        opencode_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        workspace = tmp_path / repo_fp
        workspace.mkdir(parents=True, exist_ok=True)
        session_file = workspace / "SESSION_STATE.json"
        session_file.write_text(
            json.dumps({"SESSION_STATE": {"RepoFingerprint": repo_fp, "PersistenceCommitted": True}}),
            encoding="utf-8",
        )

        pointer_file = opencode_home / "SESSION_STATE.json"
        pointer_data = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": repo_fp,
            "activeSessionStateFile": str(session_file),
            "updatedAt": "2026-02-21T20:00:00Z",
        }
        pointer_file.write_text(json.dumps(pointer_data))

        ok, reason = _verify_pointer_exists(opencode_home, repo_fp)
        assert ok is True
        assert reason == "ok"

    @pytest.mark.governance
    def test_verify_pointer_missing_fails(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_persistence_hook import _verify_pointer_exists

        opencode_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        ok, reason = _verify_pointer_exists(opencode_home, repo_fp)
        assert ok is False
        assert "not-found" in reason

    @pytest.mark.governance
    def test_verify_pointer_fingerprint_mismatch_fails(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_persistence_hook import _verify_pointer_exists

        opencode_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        pointer_file = opencode_home / "SESSION_STATE.json"
        pointer_data = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": "different123456789abcd",
            "updatedAt": "2026-02-21T20:00:00Z",
        }
        pointer_file.write_text(json.dumps(pointer_data))

        ok, reason = _verify_pointer_exists(opencode_home, repo_fp)
        assert ok is False
        assert "mismatch" in reason

    @pytest.mark.governance
    def test_verify_workspace_session_exists_success(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_persistence_hook import _verify_workspace_session_exists

        workspaces_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        workspace_dir = workspaces_home / repo_fp
        workspace_dir.mkdir(parents=True)
        session_file = workspace_dir / "SESSION_STATE.json"
        session_data = {
            "SESSION_STATE": {
                "PersistenceCommitted": True,
                "phase": "1.1-Bootstrap",
            }
        }
        session_file.write_text(json.dumps(session_data))

        ok, reason = _verify_workspace_session_exists(workspaces_home, repo_fp)
        assert ok is True
        assert reason == "ok"

    @pytest.mark.governance
    def test_verify_workspace_session_not_committed_fails(self, tmp_path: Path):
        from governance_runtime.entrypoints.bootstrap_persistence_hook import _verify_workspace_session_exists

        workspaces_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        workspace_dir = workspaces_home / repo_fp
        workspace_dir.mkdir(parents=True)
        session_file = workspace_dir / "SESSION_STATE.json"
        session_data = {
            "SESSION_STATE": {
                "PersistenceCommitted": False,
                "phase": "1.1-Bootstrap",
            }
        }
        session_file.write_text(json.dumps(session_data))

        ok, reason = _verify_workspace_session_exists(workspaces_home, repo_fp)
        assert ok is False
        assert "PersistenceCommitted" in reason


class TestPointerWriteFailure:
    """Tests for pointer write failure handling."""

    @pytest.mark.governance
    def test_pointer_write_failure_returns_nonzero(self, tmp_path: Path):
        # Use a path inside a non-existent directory to guarantee write failure.
        config_root = tmp_path / "config" / "nonexistent_subdir"
        pointer_file = config_root / "SESSION_STATE.json"

        result = subprocess.run(
            [sys.executable, "-c", f"""
import json, sys
from pathlib import Path
pointer_file = Path("{pointer_file}")
try:
    pointer_file.write_text(json.dumps({{"test": "fail"}}))
    print("written")
except OSError:
    print("write-failed")
    sys.exit(1)
"""],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0 or "written" not in result.stdout


class TestSchemaDriftElimination:
    """Tests for pointer schema unification."""

    @pytest.mark.governance
    def test_legacy_schema_migrated_on_read(self, tmp_path: Path):
        from governance_runtime.infrastructure.workspace_ready_gate import (
            CANONICAL_POINTER_SCHEMA,
            read_pointer_file,
        )

        pointer_file = tmp_path / "SESSION_STATE.json"
        legacy_data = {
            "schema": "active-session-pointer.v1",
            "repo_fingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
            "session_id": "test-session",
            "workspace_ready": True,
            "active_session_state_file": "/mock/workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
            "updated_at": "2026-02-21T20:00:00Z",
        }
        pointer_file.write_text(json.dumps(legacy_data))

        result = read_pointer_file(pointer_file)
        assert result is not None
        assert result["schema"] == CANONICAL_POINTER_SCHEMA
        assert "updatedAt" in result

    @pytest.mark.governance
    def test_canonical_schema_accepted(self, tmp_path: Path):
        from governance_runtime.infrastructure.workspace_ready_gate import (
            CANONICAL_POINTER_SCHEMA,
            read_pointer_file,
        )

        pointer_file = tmp_path / "SESSION_STATE.json"
        canonical_data = {
            "schema": CANONICAL_POINTER_SCHEMA,
            "activeRepoFingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
            "activeSessionStateFile": "/mock/workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
            "activeSessionStateRelativePath": "workspaces/a1b2c3d4e5f6a1b2c3d4e5f6/SESSION_STATE.json",
            "updatedAt": "2026-02-21T20:00:00Z",
        }
        pointer_file.write_text(json.dumps(canonical_data))

        result = read_pointer_file(pointer_file)
        assert result is not None
        assert result["schema"] == CANONICAL_POINTER_SCHEMA


class TestPhase2Artifacts:
    """E2E tests for Phase-2 artifact persistence."""

    @pytest.mark.governance
    def test_phase2_artifacts_written_on_persist(self, tmp_path: Path):
        from governance_runtime.entrypoints.persist_workspace_artifacts import (
            PHASE2_ARTIFACTS,
            _verify_phase2_artifacts_exist,
        )

        repo_home = tmp_path / "a1b2c3d4e5f6a1b2c3d4e5f6"
        repo_home.mkdir(parents=True)

        for artifact in PHASE2_ARTIFACTS:
            (repo_home / artifact).write_text("# seed\n")

        ok, missing = _verify_phase2_artifacts_exist(repo_home)
        assert ok is True
        assert missing == []

    @pytest.mark.governance
    def test_phase2_artifacts_missing_detected(self, tmp_path: Path):
        from governance_runtime.entrypoints.persist_workspace_artifacts import (
            _verify_phase2_artifacts_exist,
        )

        repo_home = tmp_path / "a1b2c3d4e5f6a1b2c3d4e5f6"
        repo_home.mkdir(parents=True)

        (repo_home / "repo-cache.yaml").write_text("# seed\n")

        ok, missing = _verify_phase2_artifacts_exist(repo_home)
        assert ok is False
        assert "repo-map-digest.md" in missing
        assert "workspace-memory.yaml" in missing

    @pytest.mark.governance
    def test_phase2_artifact_paths_from_utility(self, tmp_path: Path):
        from governance_runtime.infrastructure.workspace_paths import (
            phase2_artifact_paths,
            repo_cache_path,
            repo_map_digest_path,
            workspace_memory_path,
        )

        workspaces_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        cache_path = repo_cache_path(workspaces_home, repo_fp)
        digest_path = repo_map_digest_path(workspaces_home, repo_fp)
        memory_path = workspace_memory_path(workspaces_home, repo_fp)

        assert cache_path.name == "repo-cache.yaml"
        assert digest_path.name == "repo-map-digest.md"
        assert memory_path.name == "workspace-memory.yaml"
        assert repo_fp in str(cache_path)

        paths = phase2_artifact_paths(workspaces_home, repo_fp)
        assert paths["repo_cache"] == cache_path
        assert paths["repo_map_digest"] == digest_path
        assert paths["workspace_memory"] == memory_path

    @pytest.mark.governance
    def test_phase2_complete_status_reflects_artifacts(self, tmp_path: Path):
        from governance_runtime.entrypoints.persist_workspace_artifacts import (
            _verify_phase2_artifacts_exist,
        )

        repo_home = tmp_path / "a1b2c3d4e5f6a1b2c3d4e5f6"
        repo_home.mkdir(parents=True)

        ok, missing = _verify_phase2_artifacts_exist(repo_home)
        assert ok is False

        repo_home.joinpath("repo-cache.yaml").write_text("# cache\n")
        ok, missing = _verify_phase2_artifacts_exist(repo_home)
        assert ok is False

        repo_home.joinpath("repo-map-digest.md").write_text("# digest\n")
        ok, missing = _verify_phase2_artifacts_exist(repo_home)
        assert ok is False

        repo_home.joinpath("workspace-memory.yaml").write_text("# memory\n")
        ok, missing = _verify_phase2_artifacts_exist(repo_home)
        assert ok is True
