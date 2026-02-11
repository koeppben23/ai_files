from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from governance.engine.adapters import HostCapabilities
from governance.engine.orchestrator import run_engine_orchestrator


@dataclass(frozen=True)
class StubAdapter:
    """Deterministic in-memory adapter used by orchestrator tests."""

    env: dict[str, str]
    cwd_path: Path
    caps: HostCapabilities

    def capabilities(self) -> HostCapabilities:
        return self.caps

    def environment(self) -> dict[str, str]:
        return self.env

    def cwd(self) -> Path:
        return self.cwd_path.resolve()


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
        caps=HostCapabilities(cwd_trust="trusted", fs_read=True, git_available=False),
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
        "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
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
        caps=HostCapabilities(cwd_trust="untrusted", fs_read=True, git_available=False),
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
        caps=HostCapabilities(cwd_trust="trusted", fs_read=True, git_available=True),
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
