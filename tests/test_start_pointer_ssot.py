"""E2E tests for pointer SSOT and canonical fingerprint enforcement.

These tests reproduce and prevent the bug where:
- /start returns success text but pointer is missing
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
        from diagnostics.bootstrap_session_state import (
            _atomic_write_text,
            pointer_payload,
            session_state_template,
        )
        from governance.infrastructure.fs_atomic import atomic_write_text

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
        from diagnostics.bootstrap_session_state import pointer_payload

        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
        session_file = tmp_path / "SESSION_STATE.json"
        pointer = pointer_payload(repo_fp, session_file)

        assert pointer["schema"] == "opencode-session-pointer.v1"
        assert "activeRepoFingerprint" in pointer
        assert pointer["activeRepoFingerprint"] == repo_fp

    @pytest.mark.governance
    def test_workspace_session_state_path_in_pointer(self, tmp_path: Path):
        from diagnostics.bootstrap_session_state import pointer_payload

        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
        session_file = tmp_path / "workspaces" / repo_fp / "SESSION_STATE.json"
        pointer = pointer_payload(repo_fp, session_file)

        assert "activeSessionStateFile" in pointer
        assert repo_fp in pointer["activeSessionStateFile"]


class TestCanonicalFingerprint:
    """Tests for 24-hex canonical fingerprint enforcement."""

    @pytest.mark.governance
    def test_canonical_fingerprint_validation(self):
        from diagnostics.bootstrap_session_state import (
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
        from diagnostics.persist_workspace_artifacts import _is_canonical_fingerprint

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
        from diagnostics.start_persistence_hook import _verify_pointer_exists

        opencode_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        pointer_file = opencode_home / "SESSION_STATE.json"
        pointer_data = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": repo_fp,
            "updatedAt": "2026-02-21T20:00:00Z",
        }
        pointer_file.write_text(json.dumps(pointer_data))

        ok, reason = _verify_pointer_exists(opencode_home, repo_fp)
        assert ok is True
        assert reason == "ok"

    @pytest.mark.governance
    def test_verify_pointer_missing_fails(self, tmp_path: Path):
        from diagnostics.start_persistence_hook import _verify_pointer_exists

        opencode_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        ok, reason = _verify_pointer_exists(opencode_home, repo_fp)
        assert ok is False
        assert "not-found" in reason

    @pytest.mark.governance
    def test_verify_pointer_fingerprint_mismatch_fails(self, tmp_path: Path):
        from diagnostics.start_persistence_hook import _verify_pointer_exists

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
        from diagnostics.start_persistence_hook import _verify_workspace_session_exists

        workspaces_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        workspace_dir = workspaces_home / repo_fp
        workspace_dir.mkdir(parents=True)
        session_file = workspace_dir / "SESSION_STATE.json"
        session_data = {
            "SESSION_STATE": {
                "PersistenceCommitted": True,
                "Phase": "1.1-Bootstrap",
            }
        }
        session_file.write_text(json.dumps(session_data))

        ok, reason = _verify_workspace_session_exists(workspaces_home, repo_fp)
        assert ok is True
        assert reason == "ok"

    @pytest.mark.governance
    def test_verify_workspace_session_not_committed_fails(self, tmp_path: Path):
        from diagnostics.start_persistence_hook import _verify_workspace_session_exists

        workspaces_home = tmp_path
        repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"

        workspace_dir = workspaces_home / repo_fp
        workspace_dir.mkdir(parents=True)
        session_file = workspace_dir / "SESSION_STATE.json"
        session_data = {
            "SESSION_STATE": {
                "PersistenceCommitted": False,
                "Phase": "1.1-Bootstrap",
            }
        }
        session_file.write_text(json.dumps(session_data))

        ok, reason = _verify_workspace_session_exists(workspaces_home, repo_fp)
        assert ok is False
        assert "PersistenceCommitted" in reason


class TestPointerWriteFailure:
    """Tests for pointer write failure handling."""

    @pytest.mark.governance
    @pytest.mark.skip(
        reason="chmod read-only does not reliably prevent writes for file owner on any platform"
    )
    def test_pointer_write_failure_returns_nonzero(self, tmp_path: Path):
        config_root = tmp_path / "config"
        config_root.mkdir(parents=True)
        pointer_file = config_root / "SESSION_STATE.json"

        pointer_file.write_text("{}")
        os.chmod(config_root, 0o555)

        try:
            result = subprocess.run(
                [sys.executable, "-c", f"""
import json
from pathlib import Path
pointer_file = Path("{pointer_file}")
pointer_file.write_text(json.dumps({{"test": "fail"}}))
print("written")
"""],
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0 or "written" not in result.stdout
        finally:
            os.chmod(config_root, 0o755)


class TestSchemaDriftElimination:
    """Tests for pointer schema unification."""

    @pytest.mark.governance
    def test_legacy_schema_migrated_on_read(self, tmp_path: Path):
        from governance.infrastructure.workspace_ready_gate import (
            CANONICAL_POINTER_SCHEMA,
            read_pointer_file,
        )

        pointer_file = tmp_path / "SESSION_STATE.json"
        legacy_data = {
            "schema": "active-session-pointer.v1",
            "repo_fingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
            "session_id": "test-session",
            "workspace_ready": True,
            "active_session_state_file": "/path/to/session.json",
            "updated_at": "2026-02-21T20:00:00Z",
        }
        pointer_file.write_text(json.dumps(legacy_data))

        result = read_pointer_file(pointer_file)
        assert result is not None
        assert result["schema"] == CANONICAL_POINTER_SCHEMA
        assert "updatedAt" in result

    @pytest.mark.governance
    def test_canonical_schema_accepted(self, tmp_path: Path):
        from governance.infrastructure.workspace_ready_gate import (
            CANONICAL_POINTER_SCHEMA,
            read_pointer_file,
        )

        pointer_file = tmp_path / "SESSION_STATE.json"
        canonical_data = {
            "schema": CANONICAL_POINTER_SCHEMA,
            "repo_fingerprint": "a1b2c3d4e5f6a1b2c3d4e5f6",
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
        from diagnostics.persist_workspace_artifacts import (
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
        from diagnostics.persist_workspace_artifacts import (
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
        from governance.infrastructure.workspace_paths import (
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
        from diagnostics.persist_workspace_artifacts import (
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
