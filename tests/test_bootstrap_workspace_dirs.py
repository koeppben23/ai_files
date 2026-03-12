"""Tests for Defects 3 & 4a: runtime logs and archive runs directories are created.

Defect 3: The workspace-scoped ``logs/`` directory was never created during
bootstrap, causing the error logger to fall back to the global
``commands/logs`` path.

Defect 4a: Archived runs must live under
``workspaces/governance-records/<fp>/runs`` (not ``workspaces/<fp>/runs``).
Bootstrap pre-creates this archive root to keep the layout deterministic.

Both directories are now created via ``fs.mkdir_p()`` immediately after the
initial SESSION_STATE and identity-map writes, before the ``no_commit``
early-exit guard.

These tests cover Happy / Bad / Corner / Edge scenarios.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governance.application.use_cases.bootstrap_persistence import (
    ACTIVATION_INTENT_FILE,
    BootstrapInput,
    BootstrapPersistenceService,
)
from governance.domain.models.binding import Binding
from governance.domain.models.layouts import WorkspaceLayout
from governance.domain.models.repo_identity import RepoIdentity
from governance.infrastructure.adapters.filesystem.in_memory import InMemoryFS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ACTIVATION_INTENT = {
    "schema": "opencode-activation-intent.v1",
    "discovery_scope": "full",
    "discovery_patterns": [],
    "discovery_excludes": [],
    "default_scope": "governance-pipeline-only",
    "allowed_actions": {
        "read_only": True,
        "write_allowed_in_user_mode": True,
    },
    "default_question_policy": {
        "no_questions_before_phase4": True,
        "blocked_when_no_safe_default": True,
    },
    "single_dev_mode": True,
}

_FP = "abcdef0123456789abcdef01"
_WORKSPACE = f"/mock/config/workspaces/{_FP}"


def _archive_runs_dir() -> Path:
    return Path(f"/mock/config/workspaces/governance-records/{_FP}/runs")


class _DummyRunner:
    class _Result:
        def __init__(self, rc: int = 0) -> None:
            self.returncode = rc
            self.stdout = ""
            self.stderr = ""

    def __init__(self, *, returncode: int = 0) -> None:
        self._rc = returncode

    def run(self, argv, env=None):
        _ = argv, env
        return _DummyRunner._Result(self._rc)


class _DummyLogger:
    def __init__(self) -> None:
        self.events: list[object] = []

    def write(self, event: object) -> None:
        self.events.append(event)


def _payload(*, mode: str = "user", no_commit: bool = True,
             skip_backfill: bool = False,
             required_artifacts: tuple[str, ...] = ()) -> BootstrapInput:
    return BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root="/mock/repo",
            fingerprint="abcdef0123456789abcdef01",
            repo_name="repo",
            source="test",
        ),
        binding=Binding(
            config_root="/mock/config",
            commands_home="/mock/config/commands",
            workspaces_home="/mock/config/workspaces",
            python_command="python3",
        ),
        layout=WorkspaceLayout(
            repo_home=_WORKSPACE,
            session_state_file=f"{_WORKSPACE}/SESSION_STATE.json",
            identity_map_file=f"{_WORKSPACE}/repo-identity-map.yaml",
            pointer_file="/mock/config/SESSION_STATE.json",
        ),
        required_artifacts=required_artifacts,
        effective_mode=mode,
        write_policy_reasons=(),
        no_commit=no_commit,
        skip_artifact_backfill=skip_backfill,
    )


def _seed_valid_intent(fs: InMemoryFS) -> None:
    path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
    fs.write_text_atomic(path, json.dumps(_VALID_ACTIVATION_INTENT))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Both logs/ and governance archive runs/ are created during bootstrap."""

    def test_logs_dir_created(self):
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))

    def test_archive_runs_dir_created(self):
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        assert fs.dir_exists(_archive_runs_dir())

    def test_write_actions_records_workspace_dirs(self):
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        assert result.write_actions.get("workspace_dirs") == "ensured"

    def test_user_mode_auto_creates_intent_and_dirs(self):
        """In user mode without a pre-existing intent file, both the intent
        and workspace dirs are created."""
        fs = InMemoryFS()
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())


# ---------------------------------------------------------------------------
# Bad-path tests
# ---------------------------------------------------------------------------


class TestBadPath:
    """Dirs are NOT created when bootstrap fails before reaching the mkdir step."""

    def test_missing_intent_outside_user_mode_no_dirs(self):
        """Bootstrap fails before dir creation — no dirs should exist."""
        fs = InMemoryFS()
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="pipeline", no_commit=True), _now())

        assert result.ok is False
        assert not fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert not fs.dir_exists(_archive_runs_dir())

    def test_invalid_intent_no_dirs(self):
        """Invalid intent causes early exit before dir creation."""
        fs = InMemoryFS()
        path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
        fs.write_text_atomic(path, json.dumps({"schema": "wrong"}))
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is False
        assert not fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert not fs.dir_exists(_archive_runs_dir())


# ---------------------------------------------------------------------------
# Corner-case tests
# ---------------------------------------------------------------------------


class TestCornerCases:

    def test_dirs_created_before_no_commit_exit(self):
        """With no_commit=True the service exits early, but dirs are still created
        because mkdir happens before the no_commit guard."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        assert result.write_actions.get("no_commit") == "true"
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())

    def test_dirs_created_even_on_backfill_failure(self):
        """Backfill fails (non-zero exit) but the dirs were already created
        before backfill runs."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(  # type: ignore[arg-type]
            fs=fs,
            runner=_DummyRunner(returncode=1),  # pyright: ignore[reportArgumentType]
            logger=_DummyLogger(),
        )

        result = svc.run(
            _payload(mode="user", no_commit=False, skip_backfill=False),
            _now(),
        )

        assert result.ok is False
        assert result.gate_code == "BACKFILL_NON_ZERO_EXIT"
        # Dirs were created before backfill
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())

    def test_dirs_created_even_on_missing_artifacts(self):
        """Required artifacts check fails but dirs were already created."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(
            _payload(
                mode="user",
                no_commit=False,
                skip_backfill=True,
                required_artifacts=(f"{_WORKSPACE}/nonexistent.json",),
            ),
            _now(),
        )

        assert result.ok is False
        assert result.gate_code == "PHASE2_ARTIFACTS_MISSING"
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())

    def test_pipeline_mode_with_valid_intent_creates_dirs(self):
        """Pipeline mode with a valid intent must also create dirs."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="pipeline", no_commit=True), _now())

        assert result.ok is True
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_idempotent_mkdir(self):
        """Running bootstrap twice does not fail — mkdir_p is idempotent."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result1 = svc.run(_payload(mode="user", no_commit=True), _now())
        # Second run: intent file now exists (was auto-created or pre-seeded)
        _seed_valid_intent(fs)
        result2 = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result1.ok is True
        assert result2.ok is True
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())

    def test_dirs_are_under_correct_workspace(self):
        """The dirs are created under the workspace root from the layout,
        not under config_root or workspaces_home."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        svc.run(_payload(mode="user", no_commit=True), _now())

        # Should NOT be under config_root
        assert not fs.dir_exists(Path("/mock/config/logs"))
        assert not fs.dir_exists(Path("/mock/config/runs"))
        # Should NOT be under workspaces_home
        assert not fs.dir_exists(Path("/mock/config/workspaces/logs"))
        assert not fs.dir_exists(Path("/mock/config/workspaces/runs"))
        # SHOULD be under repo_home (the workspace root)
        assert fs.dir_exists(Path(f"{_WORKSPACE}/logs"))
        assert fs.dir_exists(_archive_runs_dir())
        assert not fs.dir_exists(Path(f"{_WORKSPACE}/runs"))

    def test_no_current_run_json_sentinel(self):
        """Defect 4a hardening: archive runs root is created and no sentinel is written."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        svc.run(_payload(mode="user", no_commit=True), _now())

        assert fs.dir_exists(_archive_runs_dir())
        assert not fs.exists(Path(f"{_WORKSPACE}/current_run.json"))

    def test_session_state_still_written_alongside_dirs(self):
        """Dir creation does not interfere with the SESSION_STATE write."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        assert fs.exists(Path(f"{_WORKSPACE}/SESSION_STATE.json"))
        state = json.loads(fs.read_text(Path(f"{_WORKSPACE}/SESSION_STATE.json")))
        assert "SESSION_STATE" in state
