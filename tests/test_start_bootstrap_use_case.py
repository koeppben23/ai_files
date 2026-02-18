from __future__ import annotations

from pathlib import Path

import pytest

from governance.application.use_cases.start_bootstrap import evaluate_start_identity
from governance.engine.adapters import ExecResult, HostCapabilities


class StubAdapter:
    def __init__(self, *, env: dict[str, str], cwd_path: Path, top_level_result: ExecResult, origin_result: ExecResult):
        self._env = env
        self._cwd = cwd_path
        self._top_level_result = top_level_result
        self._origin_result = origin_result

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
            return self._origin_result
        return self._top_level_result


@pytest.mark.governance
def test_start_identity_returns_unresolved_when_cwd_is_not_git_repo(tmp_path: Path):
    non_repo = tmp_path / "backup"
    non_repo.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={},
        cwd_path=non_repo,
        top_level_result=ExecResult(argv=("git",), cwd=str(non_repo), exit_code=128, stdout="", stderr="not a git repo"),
        origin_result=ExecResult(argv=("git",), cwd=str(non_repo), exit_code=128, stdout="", stderr="not a git repo"),
    )

    result = evaluate_start_identity(adapter=adapter)

    assert result.workspace_ready is False
    assert result.repo_root is None
    assert result.repo_fingerprint == ""
    assert result.reason_code == "BLOCKED-REPO-IDENTITY-RESOLUTION"


@pytest.mark.governance
def test_start_identity_derives_fingerprint_from_git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(repo)},
        cwd_path=repo,
        top_level_result=ExecResult(argv=("git",), cwd=str(repo), exit_code=0, stdout=str(repo) + "\n", stderr=""),
        origin_result=ExecResult(argv=("git",), cwd=str(repo), exit_code=0, stdout="git@github.com:org/proj.git\n", stderr=""),
    )

    result = evaluate_start_identity(adapter=adapter)

    assert result.workspace_ready is True
    assert result.repo_root == repo.resolve()
    assert isinstance(result.repo_fingerprint, str) and result.repo_fingerprint.strip()
    assert result.reason_code == "none"
