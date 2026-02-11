from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from governance.engine.adapters import HostCapabilities, OperatingMode
from governance.engine.orchestrator import run_engine_orchestrator


@dataclass(frozen=True)
class StubAdapter:
    """Deterministic in-memory adapter used by orchestrator tests."""

    env: dict[str, str]
    cwd_path: Path
    caps: HostCapabilities
    default_mode: OperatingMode = "user"

    def capabilities(self) -> HostCapabilities:
        return self.caps

    def environment(self) -> dict[str, str]:
        return self.env

    def cwd(self) -> Path:
        return self.cwd_path.resolve()

    def default_operating_mode(self) -> OperatingMode:
        return self.default_mode


def _make_git_root(path: Path) -> Path:
    """Create a minimal git root marker for deterministic context tests."""

    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


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

    assert out.repo_context.source == "cwd"
    assert out.repo_context.is_git_root is False
    assert out.parity == {
        "status": "blocked",
        "phase": "1.1-Bootstrap",
        "reason_code": "BLOCKED-REPO-IDENTITY-RESOLUTION",
        "next_action.command": "/start",
    }


@pytest.mark.governance
def test_orchestrator_uses_parent_git_root_search_for_untrusted_cwd(tmp_path: Path):
    """Untrusted cwd should enable bounded parent search via resolver contract."""

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

    assert out.repo_context.repo_root == repo_root.resolve()
    assert out.repo_context.source == "cwd-parent-search"
    assert out.repo_context.is_git_root is True
    assert out.parity["status"] == "ok"


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
    assert out.parity["status"] == "ok"
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
