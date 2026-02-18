from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governance.engine.adapters import ExecResult, HostCapabilities, OperatingMode
from governance.engine.orchestrator import run_engine_orchestrator
from governance.infrastructure.persist_confirmation_store import record_persist_confirmation
from governance.engine.reason_codes import (
    BLOCKED_ENGINE_SELFCHECK,
    NOT_VERIFIED_EVIDENCE_STALE,
    REASON_CODE_NONE,
)


@dataclass(frozen=True)
class StubAdapter:
    """Deterministic in-memory adapter used by orchestrator tests."""

    env: dict[str, str]
    cwd_path: Path
    caps: HostCapabilities
    default_mode: OperatingMode = "user"
    now_utc_value: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def capabilities(self) -> HostCapabilities:
        return self.caps

    def environment(self) -> dict[str, str]:
        return self.env

    def cwd(self) -> Path:
        return self.cwd_path.resolve()

    def default_operating_mode(self) -> OperatingMode:
        return self.default_mode

    def now_utc(self) -> datetime:
        return self.now_utc_value

    def exec_argv(self, argv, *, cwd=None, timeout_seconds=10):
        _ = timeout_seconds
        args = tuple(str(x) for x in argv)
        run_cwd = Path(cwd) if cwd is not None else self.cwd_path.resolve()
        if "--show-toplevel" in args:
            if (run_cwd / ".git").exists():
                return ExecResult(argv=args, cwd=str(run_cwd), exit_code=0, stdout=str(run_cwd) + "\n", stderr="")
            return ExecResult(argv=args, cwd=str(run_cwd), exit_code=128, stdout="", stderr="not a git repository")
        return ExecResult(argv=args, cwd=str(run_cwd), exit_code=0, stdout="", stderr="")


def _make_git_root(path: Path) -> Path:
    """Create a minimal git root marker for deterministic context tests."""

    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


def _pack_manifest(pack_id: str, *, requires: list[str] | None = None) -> dict:
    """Build minimal valid pack manifest for orchestrator lock checks."""

    return {
        "id": pack_id,
        "version": "1.0.0",
        "compat": {"engine_min": "1.0.0", "engine_max": "9.9.9"},
        "requires": requires or [],
        "conflicts_with": [],
    }


@pytest.mark.governance
def test_orchestrator_blocks_when_cwd_is_not_git_root_and_git_is_unavailable(tmp_path: Path):
    """Wrong cwd + missing git should produce deterministic blocked parity fields."""

    cwd = tmp_path / "outside-repo"
    cwd.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={},
        cwd_path=cwd,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=False,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )

    assert out.repo_context.source == "git-unavailable"
    assert out.repo_context.is_git_root is False
    assert out.parity == {
        "status": "blocked",
        "phase": "1.1-Bootstrap",
        "reason_code": "BLOCKED-REPO-IDENTITY-RESOLUTION",
        "next_action.command": "/start",
    }


@pytest.mark.governance
def test_orchestrator_blocks_when_untrusted_cwd_has_no_git_evidence(tmp_path: Path):
    """Untrusted cwd without git availability should fail closed."""

    repo_root = _make_git_root(tmp_path / "repo")
    nested = repo_root / "a" / "b"
    nested.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={},
        cwd_path=nested,
        caps=HostCapabilities(
            cwd_trust="untrusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=False,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )

    assert out.repo_context.repo_root is None
    assert out.repo_context.source == "git-unavailable"
    assert out.repo_context.is_git_root is False
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-REPO-IDENTITY-RESOLUTION"


@pytest.mark.governance
def test_orchestrator_surfaces_write_policy_failures_as_blocking_reason(tmp_path: Path):
    """Invalid target paths should be propagated as deterministic blocking reasons."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        target_path="${UNKNOWN_VAR}/file.yaml",
    )

    assert out.write_policy.valid is False
    assert out.parity == {
        "status": "blocked",
        "phase": "1.1-Bootstrap",
        "reason_code": "BLOCKED-PERSISTENCE-PATH-VIOLATION",
        "next_action.command": "/start",
    }


@pytest.mark.governance
def test_orchestrator_mode_downgrade_is_reported_when_system_capabilities_missing(tmp_path: Path):
    """Requested system mode should deterministically downgrade when capabilities are insufficient."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=False,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="system",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        requested_operating_mode="system",
    )
    assert out.effective_operating_mode == "user"
    assert out.mode_downgraded is True
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-MISSING-BINDING-FILE"


@pytest.mark.governance
def test_orchestrator_user_mode_blocks_when_binding_read_capability_missing(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=False,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="user",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )

    assert out.effective_operating_mode == "user"
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-MISSING-BINDING-FILE"


@pytest.mark.governance
def test_orchestrator_resolves_pipeline_mode_from_ci_when_not_explicit(tmp_path: Path):
    """CI signal should deterministically resolve to pipeline mode."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"CI": "true", "OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="user",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )
    assert out.effective_operating_mode == "pipeline"
    assert out.mode_downgraded is False


@pytest.mark.governance
def test_orchestrator_downgrades_pipeline_mode_when_pipeline_caps_missing(tmp_path: Path):
    """Pipeline mode should downgrade to user when stricter caps are unavailable."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"CI": "true", "OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=False,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="user",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )
    assert out.effective_operating_mode == "user"
    assert out.mode_downgraded is True
    assert out.parity["reason_code"] == "WARN-MODE-DOWNGRADED"


@pytest.mark.governance
def test_orchestrator_blocks_when_exec_is_disallowed(tmp_path: Path):
    """Execution-disallowed capability must fail closed with explicit reason code."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=False,
            git_available=True,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-EXEC-DISALLOWED"


@pytest.mark.governance
def test_orchestrator_requires_system_mode_for_installer_owned_surface(tmp_path: Path):
    """User mode must not write installer-owned command surfaces even if writable."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="user",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        target_path="${COMMANDS_HOME}/master.md",
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-SYSTEM-MODE-REQUIRED"


@pytest.mark.governance
def test_orchestrator_requires_pipeline_mode_for_pointer_surface(tmp_path: Path):
    """System mode should not satisfy pipeline-only canonical pointer surface."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="system",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        requested_operating_mode="system",
        target_path="${SESSION_STATE_POINTER_FILE}",
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-OPERATING-MODE-REQUIRED"


@pytest.mark.governance
def test_orchestrator_blocks_when_required_pack_lock_is_missing(tmp_path: Path):
    """Required lock mode should fail closed when observed lock is absent."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    manifests = {
        "core": _pack_manifest("core"),
    }

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        pack_manifests_by_id=manifests,
        selected_pack_ids=["core"],
        pack_engine_version="2.0.0",
        observed_pack_lock=None,
        require_pack_lock=True,
    )
    assert out.pack_lock_checked is True
    assert out.expected_pack_lock_hash
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-PACK-LOCK-REQUIRED"


@pytest.mark.governance
def test_orchestrator_blocks_when_observed_pack_lock_hash_mismatches(tmp_path: Path):
    """Observed lock hash mismatch should fail closed deterministically."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    manifests = {
        "core": _pack_manifest("core"),
    }
    observed = {
        "schema": "governance-lock.v1",
        "lock_hash": "deadbeef",
    }

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        pack_manifests_by_id=manifests,
        selected_pack_ids=["core"],
        pack_engine_version="2.0.0",
        observed_pack_lock=observed,
        require_pack_lock=True,
    )
    assert out.pack_lock_checked is True
    assert out.observed_pack_lock_hash == "deadbeef"
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-PACK-LOCK-MISMATCH"


@pytest.mark.governance
def test_orchestrator_accepts_matching_pack_lock(tmp_path: Path):
    """Matching lock payload should keep parity status non-blocking."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    manifests = {
        "core": _pack_manifest("core"),
        "addon": _pack_manifest("addon", requires=["core"]),
    }

    expected = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        pack_manifests_by_id=manifests,
        selected_pack_ids=["addon"],
        pack_engine_version="2.0.0",
    )

    observed = {
        "schema": "governance-lock.v1",
        "lock_hash": expected.expected_pack_lock_hash,
    }
    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        pack_manifests_by_id=manifests,
        selected_pack_ids=["addon"],
        pack_engine_version="2.0.0",
        observed_pack_lock=observed,
        require_pack_lock=True,
    )
    assert out.pack_lock_checked is True
    assert out.expected_pack_lock_hash == expected.expected_pack_lock_hash
    assert out.observed_pack_lock_hash == expected.expected_pack_lock_hash
    assert out.parity["status"] == "ok"


@pytest.mark.governance
def test_orchestrator_maps_pack_surface_conflict_to_canonical_reason(tmp_path: Path):
    """Pack surface ownership conflicts should map to BLOCKED-SURFACE-CONFLICT."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    manifests = {
        "core-a": {
            "id": "core-a",
            "version": "1.0.0",
            "compat": {"engine_min": "1.0.0", "engine_max": "9.9.9"},
            "requires": [],
            "conflicts_with": [],
            "owns_surfaces": ["session_state"],
            "touches_surfaces": [],
        },
        "core-b": {
            "id": "core-b",
            "version": "1.0.0",
            "compat": {"engine_min": "1.0.0", "engine_max": "9.9.9"},
            "requires": [],
            "conflicts_with": [],
            "owns_surfaces": ["session_state"],
            "touches_surfaces": [],
        },
    }

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        pack_manifests_by_id=manifests,
        selected_pack_ids=["core-a", "core-b"],
        pack_engine_version="2.0.0",
        require_pack_lock=True,
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-SURFACE-CONFLICT"


@pytest.mark.governance
def test_orchestrator_blocks_on_ruleset_hash_mismatch_when_required(tmp_path: Path):
    """Ruleset hash mismatch should fail closed when hash match is required."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        require_hash_match=True,
        observed_ruleset_hash="deadbeef",
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-RULESET-HASH-MISMATCH"


@pytest.mark.governance
def test_orchestrator_blocks_on_activation_hash_mismatch_when_required(tmp_path: Path):
    """Activation hash mismatch should fail closed when hash match is required."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        require_hash_match=True,
        observed_ruleset_hash="",  # skip ruleset mismatch branch
        observed_activation_hash="deadbeef",
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-ACTIVATION-HASH-MISMATCH"


@pytest.mark.governance
def test_orchestrator_marks_not_verified_when_required_evidence_missing(tmp_path: Path):
    """Missing required evidence should produce NOT_VERIFIED status."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        required_evidence_ids=["ev-1", "ev-2"],
        observed_evidence_ids=["ev-1"],
    )
    assert out.parity["status"] == "not_verified"
    assert out.parity["reason_code"] == "NOT_VERIFIED-MISSING-EVIDENCE"
    assert out.missing_evidence == ("ev-2",)
    assert out.reason_payload["status"] == "NOT_VERIFIED"


@pytest.mark.governance
def test_orchestrator_enforces_no_claim_without_evidence_for_quality_claims(tmp_path: Path):
    """Quality claims must remain NOT_VERIFIED unless claim evidence is present."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    required_claim_evidence = [
        "claim/tests-green",
        "claim/static-clean",
        "claim/no-drift",
    ]

    missing = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        required_evidence_ids=required_claim_evidence,
        observed_evidence_ids=["claim/tests-green"],
    )
    assert missing.parity["status"] == "not_verified"
    assert missing.parity["reason_code"] == "NOT_VERIFIED-MISSING-EVIDENCE"
    assert missing.missing_evidence == ("claim/no-drift", "claim/static-clean")
    assert missing.reason_payload["status"] == "NOT_VERIFIED"
    assert missing.reason_payload["missing_evidence"] == ("claim/no-drift", "claim/static-clean")

    satisfied = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        required_evidence_ids=required_claim_evidence,
        observed_evidence_ids=required_claim_evidence,
    )
    assert satisfied.parity["status"] == "ok"
    assert satisfied.parity["reason_code"] == REASON_CODE_NONE
    assert satisfied.reason_payload["status"] == "OK"


@pytest.mark.governance
def test_orchestrator_backfeeds_claim_evidence_from_session_state_build_evidence(tmp_path: Path):
    """Claim verification should derive from SESSION_STATE build evidence items."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    now = datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc)
    session_state = {
        "SESSION_STATE": {
            "BuildEvidence": {
                "items": [
                    {"claim": "tests green", "result": "pass", "observed_at": now.isoformat()},
                    {"claim": "static clean", "result": "pass", "observed_at": now.isoformat()},
                    {"claim": "no drift", "result": "fail", "observed_at": now.isoformat()},
                ]
            }
        }
    }
    required_claims = ["claim/tests-green", "claim/static-clean", "claim/no-drift"]

    missing = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        required_claim_evidence_ids=required_claims,
        session_state_document=session_state,
        now_utc=now,
    )
    assert missing.parity["status"] == "not_verified"
    assert missing.parity["reason_code"] == "NOT_VERIFIED-MISSING-EVIDENCE"
    assert missing.missing_evidence == ("claim/no-drift",)

    session_state["SESSION_STATE"]["BuildEvidence"]["items"][2]["result"] = "pass"
    satisfied = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        required_claim_evidence_ids=required_claims,
        session_state_document=session_state,
        now_utc=now,
    )
    assert satisfied.parity["status"] == "ok"
    assert satisfied.parity["reason_code"] == REASON_CODE_NONE


@pytest.mark.governance
def test_orchestrator_marks_not_verified_when_claim_evidence_is_stale(tmp_path: Path):
    """Stale claim evidence should produce deterministic stale-evidence not-verified reason."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )
    now = datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc)
    stale_time = (now - timedelta(days=2)).isoformat()
    session_state = {
        "SESSION_STATE": {
            "BuildEvidence": {
                "items": [
                    {
                        "claim": "tests green",
                        "result": "pass",
                        "observed_at": stale_time,
                        "evidence_class": "gate_evidence",
                    }
                ]
            }
        }
    }

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        required_claim_evidence_ids=["claim/tests-green"],
        session_state_document=session_state,
        now_utc=now,
    )

    assert out.parity["status"] == "not_verified"
    assert out.parity["reason_code"] == NOT_VERIFIED_EVIDENCE_STALE
    assert out.missing_evidence == ("claim/tests-green",)


@pytest.mark.governance
def test_orchestrator_blocks_on_release_hygiene_violation_in_pipeline_mode(tmp_path: Path):
    """Pipeline/system modes should fail closed on release hygiene violations."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"CI": "true", "OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
        default_mode="pipeline",
    )
    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
        release_hygiene_entries=("__MACOSX/file",),
    )
    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-RELEASE-HYGIENE"


@pytest.mark.governance
def test_orchestrator_emits_valid_blocked_reason_payload_shape(tmp_path: Path):
    """Blocked outputs should emit one-action/one-recovery-step/one-command shape."""

    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=False,
            git_available=True,
        ),
    )
    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )
    payload = out.reason_payload
    assert payload["status"] == "BLOCKED"
    assert payload["surface"] == "${WORKSPACE_MEMORY_FILE}"
    assert isinstance(payload["signals_used"], tuple)
    assert isinstance(payload["primary_action"], str) and payload["primary_action"].strip()
    assert isinstance(payload["recovery_steps"], tuple) and len(payload["recovery_steps"]) == 1
    assert isinstance(payload["next_command"], str) and payload["next_command"].strip()


@pytest.mark.governance
def test_orchestrator_falls_back_to_engine_selfcheck_when_payload_builder_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    def _raise(*args: object, **kwargs: object):
        raise ValueError("invalid reason payload:blocked_primary_action_required")

    monkeypatch.setattr("governance.engine.orchestrator.build_reason_payload", _raise)

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )

    payload = out.reason_payload
    assert payload["status"] == "BLOCKED"
    assert payload["reason_code"] == BLOCKED_ENGINE_SELFCHECK
    assert payload["next_command"] == "show diagnostics"
    deviation = payload.get("deviation")
    assert isinstance(deviation, dict)
    assert deviation["failure_class"] == "reason_payload_invalid"
    assert deviation["failure_detail"] == "schema_or_contract_violation"


@pytest.mark.governance
def test_orchestrator_fallback_does_not_leak_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    def _raise(*args: object, **kwargs: object):
        raise ValueError("reason_schema_missing:/abs/private/path/schema.json")

    monkeypatch.setattr("governance.engine.orchestrator.build_reason_payload", _raise)

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="1.1-Bootstrap",
        active_gate="Persistence Preflight",
        mode="OK",
        next_gate_condition="Persistence helper execution completed",
    )

    payload = out.reason_payload
    assert payload["status"] == "BLOCKED"
    assert payload["reason_code"] == BLOCKED_ENGINE_SELFCHECK
    assert payload["deviation"] == {
        "failure_class": "reason_schema_missing",
        "failure_detail": "embedded_or_disk_schema_missing",
    }
    assert "/abs/private/path" not in str(payload)


@pytest.mark.governance
def test_orchestrator_commits_workspace_ready_gate_when_requested(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    workspaces_home = tmp_path / "workspaces"
    session_state_file = workspaces_home / "abc123def456abc123def456" / "SESSION_STATE.json"
    session_state_file.parent.mkdir(parents=True, exist_ok=True)
    session_state_file.write_text("{}\n", encoding="utf-8")
    session_pointer_file = tmp_path / "SESSION_STATE.json"

    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    _ = run_engine_orchestrator(
        adapter=adapter,
        phase="2-Discovery",
        active_gate="Discovery",
        mode="OK",
        next_gate_condition="continue",
        session_state_document={"SESSION_STATE": {"repo_fingerprint": "abc123def456abc123def456"}},
        commit_workspace_ready_gate=True,
        workspaces_home=str(workspaces_home),
        session_state_file=str(session_state_file),
        session_pointer_file=str(session_pointer_file),
        session_id="sess-1",
    )

    marker = workspaces_home / "abc123def456abc123def456" / "marker.json"
    evidence = workspaces_home / "abc123def456abc123def456" / "evidence" / "repo-context.resolved.json"
    assert marker.exists()
    assert evidence.exists()
    assert session_pointer_file.exists()


@pytest.mark.governance
def test_orchestrator_blocks_workspace_memory_before_phase5(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="4-Planning",
        active_gate="Planning",
        mode="OK",
        next_gate_condition="Plan approved",
        target_path="${WORKSPACE_MEMORY_FILE}",
        session_state_document={"SESSION_STATE": {"workspace_ready_gate_committed": True, "phase_transition_evidence": True}},
        persistence_write_requested=True,
    )

    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "PERSIST_PHASE_MISMATCH"


@pytest.mark.governance
def test_orchestrator_blocks_workspace_memory_without_exact_confirmation(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="5-ImplementationQA",
        active_gate="P5",
        mode="OK",
        next_gate_condition="Persist memory",
        target_path="${WORKSPACE_MEMORY_FILE}",
        session_state_document={
            "SESSION_STATE": {
                "workspace_ready_gate_committed": True,
                "phase_transition_evidence": True,
                "phase5_approved": True,
            }
        },
        persistence_write_requested=True,
    )

    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "PERSIST_CONFIRMATION_REQUIRED"


@pytest.mark.governance
def test_orchestrator_allows_workspace_memory_with_exact_confirmation(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    evidence = tmp_path / "workspaces" / "abc" / "evidence" / "persist_confirmations.json"
    _ = record_persist_confirmation(
        evidence_path=evidence,
        scope="workspace-memory",
        gate="phase5",
        value="YES",
        mode="user",
        reason="operator-confirmed",
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="5-ImplementationQA",
        active_gate="P5",
        mode="OK",
        next_gate_condition="Persist memory",
        target_path="${WORKSPACE_MEMORY_FILE}",
        session_state_document={
            "SESSION_STATE": {
                "workspace_ready_gate_committed": True,
                "phase_transition_evidence": True,
                "phase5_approved": True,
            }
        },
        persistence_write_requested=True,
        persist_confirmation_evidence_path=str(evidence),
    )

    assert out.parity["status"] == "ok"
    assert out.parity["reason_code"] in {"none", "WARN-MODE-DOWNGRADED"}


@pytest.mark.governance
def test_orchestrator_pipeline_blocks_when_workspace_memory_confirmation_missing(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root), "CI": "true"},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="5-ImplementationQA",
        active_gate="P5",
        mode="OK",
        next_gate_condition="Persist memory",
        target_path="${WORKSPACE_MEMORY_FILE}",
        session_state_document={
            "SESSION_STATE": {
                "workspace_ready_gate_committed": True,
                "phase_transition_evidence": True,
                "phase5_approved": True,
            }
        },
        persistence_write_requested=True,
    )

    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "PERSIST_DISALLOWED_IN_PIPELINE"


@pytest.mark.governance
def test_orchestrator_blocks_code_output_requests_in_phase4(tmp_path: Path):
    repo_root = _make_git_root(tmp_path / "repo")
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo_root)},
        cwd_path=repo_root,
        caps=HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        ),
    )

    out = run_engine_orchestrator(
        adapter=adapter,
        phase="4-Planning",
        active_gate="Planning",
        mode="OK",
        next_gate_condition="Plan approved",
        session_state_document={"SESSION_STATE": {"workspace_ready_gate_committed": True, "phase_transition_evidence": True}},
        requested_action="implement now",
    )

    assert out.parity["status"] == "blocked"
    assert out.parity["reason_code"] == "BLOCKED-STATE-OUTDATED"
