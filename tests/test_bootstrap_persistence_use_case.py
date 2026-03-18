from __future__ import annotations

from pathlib import Path

import pytest

from governance.application.use_cases.bootstrap_persistence import decide_bootstrap_persistence
from typing import cast
from governance.application.ports.gateways import HostAdapter
from governance.engine.adapters import ExecResult
from tests.test_engine_orchestrator import HostCapabilities
from governance.infrastructure.wiring import configure_gateway_registry


@pytest.fixture(autouse=True)
def _configure_gateways() -> None:
    configure_gateway_registry()


class StubAdapter:
    def __init__(self, *, env: dict[str, str], cwd_path: Path, top_level: ExecResult, origin: ExecResult):
        self._env = env
        self._cwd = cwd_path
        self._top_level = top_level
        self._origin = origin

    def capabilities(self) -> HostCapabilities:
        return HostCapabilities(
            cwd_trust="trusted",
            fs_read_commands_home=True,
            fs_write_config_root=True,
            fs_write_commands_home=True,
            fs_write_workspaces_home=True,
            fs_write_repo_root=True,
            exec_allowed=True,
            git_available=True,
        )

    def environment(self) -> dict[str, str]:
        return self._env

    def cwd(self) -> Path:
        return self._cwd

    def now_utc(self):  # pragma: no cover
        raise RuntimeError("unused")

    def default_operating_mode(self):  # pragma: no cover
        return "user"

    def exec_argv(self, argv, *, cwd=None, timeout_seconds=10):
        _ = cwd, timeout_seconds
        args = tuple(str(x) for x in argv)
        if args[:2] == ("git", "-C") and args[-3:] == ("remote", "get-url", "origin"):
            return self._origin
        return self._top_level


@pytest.mark.governance
def test_bootstrap_persistence_blocks_when_repo_not_resolved(tmp_path: Path):
    non_repo = tmp_path / "backup"
    non_repo.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={},
        cwd_path=non_repo,
        top_level=ExecResult(argv=("git",), cwd=str(non_repo), exit_code=128, stdout="", stderr="not a git repo"),
        origin=ExecResult(argv=("git",), cwd=str(non_repo), exit_code=128, stdout="", stderr="not a git repo"),
    )

    decision = decide_bootstrap_persistence(adapter=cast(HostAdapter, adapter))

    assert decision.workspace_ready is False
    assert decision.repo_root is None
    assert decision.repo_fingerprint == ""
    assert decision.reason_code == "BLOCKED-REPO-IDENTITY-RESOLUTION"
    assert decision.reason == "repo-root-not-git"


@pytest.mark.governance
def test_bootstrap_persistence_resolves_workspace_ready_for_git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo)},
        cwd_path=repo,
        top_level=ExecResult(argv=("git",), cwd=str(repo), exit_code=0, stdout=str(repo) + "\n", stderr=""),
        origin=ExecResult(argv=("git",), cwd=str(repo), exit_code=0, stdout="git@github.com:org/proj.git\n", stderr=""),
    )

    decision = decide_bootstrap_persistence(adapter=cast(HostAdapter, adapter))

    assert decision.workspace_ready is True
    assert decision.repo_root == repo.resolve()
    assert isinstance(decision.repo_fingerprint, str) and decision.repo_fingerprint.strip()
    assert decision.reason_code == "none"
    assert decision.reason == "none"


@pytest.mark.governance
def test_bootstrap_persistence_unresolved_identity_never_leaks_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo)},
        cwd_path=repo,
        top_level=ExecResult(argv=("git",), cwd=str(repo), exit_code=0, stdout=str(repo) + "\n", stderr=""),
        origin=ExecResult(argv=("git",), cwd=str(repo), exit_code=0, stdout="", stderr=""),
    )

    from governance_runtime.application.use_cases import bootstrap_persistence as bp

    original = bp.evaluate_bootstrap_identity
    try:
        monkeypatch.setattr(
            bp,
            "evaluate_bootstrap_identity",
            lambda *args, **kwargs: type(
                "Identity",
                (),
                {
                    "repo_root": repo.resolve(),
                    "repo_fingerprint": "",
                    "discovery_method": "env:OPENCODE_REPO_ROOT",
                    "workspace_ready": False,
                    "reason": "identity-bootstrap-fingerprint-missing",
                },
            )(),
        )
        decision = decide_bootstrap_persistence(adapter=cast(HostAdapter, adapter))
    finally:
        monkeypatch.setattr(bp, "evaluate_bootstrap_identity", original)

    assert decision.workspace_ready is False
    assert decision.reason == "identity-bootstrap-fingerprint-missing"
    assert decision.repo_root is None
