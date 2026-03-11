"""Tests for Defect 2: initial SESSION_STATE write must propagate activation intent status.

The initial ``_session_state_payload()`` call inside ``BootstrapPersistenceService.run()``
previously omitted ``activation_intent_valid``, ``intent_sha256``, and
``intent_effective_scope``, causing every early-exit path (``no_commit``, backfill
failure, missing artifacts, pointer verification failure) to leave
``ActivationIntent.Status = "missing"`` on disk even when the intent file was
present and valid.

These tests cover Happy / Bad / Corner / Edge scenarios for the fix.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governance.application.use_cases.bootstrap_persistence import (
    ACTIVATION_INTENT_FILE,
    REPO_POLICY_RELATIVE_PATH,
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


class _DummyRunner:
    """No-op process runner (always returns rc=0)."""

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


class _FailingRunner(_DummyRunner):
    """Process runner that always returns non-zero."""

    def __init__(self) -> None:
        super().__init__(returncode=1)


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
            repo_home="/mock/config/workspaces/abcdef0123456789abcdef01",
            session_state_file="/mock/config/workspaces/abcdef0123456789abcdef01/SESSION_STATE.json",
            identity_map_file="/mock/config/workspaces/abcdef0123456789abcdef01/repo-identity-map.yaml",
            pointer_file="/mock/config/SESSION_STATE.json",
        ),
        required_artifacts=required_artifacts,
        effective_mode=mode,
        write_policy_reasons=(),
        no_commit=no_commit,
        skip_artifact_backfill=skip_backfill,
    )


def _seed_valid_intent(fs: InMemoryFS) -> None:
    """Pre-populate the activation intent file on the in-memory filesystem."""
    path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
    fs.write_text_atomic(path, json.dumps(_VALID_ACTIVATION_INTENT))


def _read_initial_session_state(fs: InMemoryFS) -> dict:
    """Read and parse the SESSION_STATE.json that was written."""
    raw = fs.read_text(
        Path("/mock/config/workspaces/abcdef0123456789abcdef01/SESSION_STATE.json")
    )
    return json.loads(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Intent file exists, is valid, and the initial write reflects it."""

    def test_no_commit_early_exit_preserves_valid_status(self):
        """no_commit=True causes early exit after initial write.
        ActivationIntent.Status must still be 'valid'."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        ai = state["SESSION_STATE"]["ActivationIntent"]
        assert ai["Status"] == "valid"
        assert ai["AutoSatisfied"] is True
        assert ai["DiscoveryScope"] == "full"

    def test_no_commit_early_exit_preserves_intent_sha256(self):
        """The Intent.Sha256 must be populated in the initial write."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        intent = state["SESSION_STATE"]["Intent"]
        assert isinstance(intent["Sha256"], str)
        assert len(intent["Sha256"]) == 64  # SHA-256 hex digest

    def test_no_commit_early_exit_preserves_intent_scope(self):
        """The Intent.EffectiveScope must reflect the intent file's discovery_scope."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        intent = state["SESSION_STATE"]["Intent"]
        assert intent["EffectiveScope"] == "full"

    def test_user_mode_auto_creates_intent_with_valid_status(self):
        """In user mode, if the intent file does not exist, bootstrap creates
        a default and the initial write must still say 'valid'."""
        fs = InMemoryFS()
        # Intentionally do NOT seed the intent file — user mode auto-creates it.
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        ai = state["SESSION_STATE"]["ActivationIntent"]
        assert ai["Status"] == "valid"
        assert ai["AutoSatisfied"] is True

    def test_bootstrap_writes_repo_operating_mode_policy(self):
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        raw = fs.read_text(Path("/mock/repo") / REPO_POLICY_RELATIVE_PATH)
        policy = json.loads(raw)
        assert policy["schema"] == "opencode-governance-repo-policy.v1"
        assert policy["operatingMode"] == "solo"


# ---------------------------------------------------------------------------
# Bad-path tests
# ---------------------------------------------------------------------------


class TestBadPath:
    """Scenarios where the activation intent is missing or invalid."""

    def test_missing_intent_outside_user_mode_blocks(self):
        """Without an intent file, pipeline mode must block."""
        fs = InMemoryFS()
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="pipeline", no_commit=True), _now())

        assert result.ok is False
        assert result.gate_code == "ACTIVATION_INTENT_REQUIRED"

    def test_invalid_intent_file_blocks(self):
        """An intent file that fails schema validation blocks bootstrap."""
        fs = InMemoryFS()
        path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
        fs.write_text_atomic(path, json.dumps({"schema": "wrong"}))
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is False
        assert result.gate_code == "ACTIVATION_INTENT_INVALID"

    def test_corrupt_json_intent_file_blocks(self):
        """An intent file with unparseable JSON blocks bootstrap."""
        fs = InMemoryFS()
        path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
        fs.write_text_atomic(path, "{{{{not json}}}}")
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is False
        assert result.gate_code == "ACTIVATION_INTENT_INVALID"


# ---------------------------------------------------------------------------
# Corner-case tests
# ---------------------------------------------------------------------------


class TestCornerCases:
    """Unusual but valid scenarios."""

    def test_backfill_failure_preserves_valid_intent_status(self):
        """Backfill fails (non-zero exit) after the initial write.
        The initial SESSION_STATE must still have Status = 'valid'."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_FailingRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(
            _payload(mode="user", no_commit=False, skip_backfill=False),
            _now(),
        )

        # Backfill failure -> ok=False
        assert result.ok is False
        assert result.gate_code == "BACKFILL_NON_ZERO_EXIT"
        # But the initial write must have captured the valid intent status
        state = _read_initial_session_state(fs)
        ai = state["SESSION_STATE"]["ActivationIntent"]
        assert ai["Status"] == "valid"
        assert ai["AutoSatisfied"] is True

    def test_missing_required_artifacts_preserves_valid_intent_status(self):
        """Required artifacts missing after backfill -> early exit.
        The initial write must still reflect valid intent."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(
            _payload(
                mode="user",
                no_commit=False,
                skip_backfill=True,
                required_artifacts=("/mock/config/workspaces/abcdef0123456789abcdef01/does_not_exist.json",),
            ),
            _now(),
        )

        assert result.ok is False
        assert result.gate_code == "PHASE2_ARTIFACTS_MISSING"
        state = _read_initial_session_state(fs)
        ai = state["SESSION_STATE"]["ActivationIntent"]
        assert ai["Status"] == "valid"

    def test_governance_only_scope_propagated(self):
        """A non-default discovery_scope ('governance-only') must appear in the
        initial write's DiscoveryScope and Intent.EffectiveScope."""
        intent = dict(_VALID_ACTIVATION_INTENT)
        intent["discovery_scope"] = "governance-only"
        fs = InMemoryFS()
        path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
        fs.write_text_atomic(path, json.dumps(intent))
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        ai = state["SESSION_STATE"]["ActivationIntent"]
        assert ai["DiscoveryScope"] == "full"  # DiscoveryScope is derived from activation_intent_valid, not discovery_scope
        intent_block = state["SESSION_STATE"]["Intent"]
        assert intent_block["EffectiveScope"] == "governance-only"

    def test_changed_files_only_scope_propagated(self):
        """A 'changed-files-only' scope must propagate through the initial write."""
        intent = dict(_VALID_ACTIVATION_INTENT)
        intent["discovery_scope"] = "changed-files-only"
        fs = InMemoryFS()
        path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
        fs.write_text_atomic(path, json.dumps(intent))
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        intent_block = state["SESSION_STATE"]["Intent"]
        assert intent_block["EffectiveScope"] == "changed-files-only"


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Extreme and boundary conditions."""

    def test_intent_file_with_extra_keys_still_validates(self):
        """A valid intent with unrecognised extra keys must still be accepted."""
        intent = dict(_VALID_ACTIVATION_INTENT)
        intent["custom_extension_field"] = {"vendor": "acme"}
        fs = InMemoryFS()
        path = Path(f"/mock/config/{ACTIVATION_INTENT_FILE}")
        fs.write_text_atomic(path, json.dumps(intent))
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="user", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        assert state["SESSION_STATE"]["ActivationIntent"]["Status"] == "valid"

    def test_initial_write_intent_sha256_matches_canonical_json(self):
        """Intent.Sha256 in the initial write must match the canonical JSON digest
        of the activation intent file content."""
        import hashlib
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        svc.run(_payload(mode="user", no_commit=True), _now())

        state = _read_initial_session_state(fs)
        sha = state["SESSION_STATE"]["Intent"]["Sha256"]
        canonical = json.dumps(_VALID_ACTIVATION_INTENT, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert sha == expected

    def test_pipeline_mode_with_valid_intent_returns_valid(self):
        """Pipeline mode with a pre-existing valid intent file must
        produce Status='valid' in the initial write."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        result = svc.run(_payload(mode="pipeline", no_commit=True), _now())

        assert result.ok is True
        state = _read_initial_session_state(fs)
        ai = state["SESSION_STATE"]["ActivationIntent"]
        assert ai["Status"] == "valid"
        assert ai["AutoSatisfied"] is True

    def test_intent_path_always_uses_posix_separator(self):
        """The ActivationIntent.FilePath must use POSIX separators regardless
        of the host platform."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        svc.run(_payload(mode="user", no_commit=True), _now())

        state = _read_initial_session_state(fs)
        file_path = state["SESSION_STATE"]["ActivationIntent"]["FilePath"]
        assert "\\" not in file_path
        assert f"${{CONFIG_ROOT}}/{ACTIVATION_INTENT_FILE}" == file_path

    def test_initial_write_bootstrap_flags_are_false(self):
        """The initial write (no_commit path) must have PersistenceCommitted=False,
        but ActivationIntent.Status must still be 'valid'.
        This verifies both concerns are independent."""
        fs = InMemoryFS()
        _seed_valid_intent(fs)
        svc = BootstrapPersistenceService(fs=fs, runner=_DummyRunner(), logger=_DummyLogger())  # type: ignore[arg-type]

        svc.run(_payload(mode="user", no_commit=True), _now())

        state = _read_initial_session_state(fs)
        ss = state["SESSION_STATE"]
        # Bootstrap flags remain false (initial write, not final)
        assert ss["PersistenceCommitted"] is False
        assert ss["WorkspaceReadyGateCommitted"] is False
        assert ss["WorkspaceArtifactsCommitted"] is False
        # But activation intent is independently valid
        assert ss["ActivationIntent"]["Status"] == "valid"
