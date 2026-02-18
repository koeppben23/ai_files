from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from governance.context.repo_context_resolver import resolve_repo_root
from governance.engine.adapters import ExecResult, HostCapabilities


@dataclass(frozen=True)
class StubAdapter:
    env: dict[str, str]
    cwd_path: Path
    caps: HostCapabilities
    result: ExecResult

    def capabilities(self) -> HostCapabilities:
        return self.caps

    def environment(self) -> dict[str, str]:
        return self.env

    def cwd(self) -> Path:
        return self.cwd_path

    def now_utc(self):  # pragma: no cover - not used in these tests
        raise RuntimeError("unused")

    def default_operating_mode(self):  # pragma: no cover - not used
        return "user"

    def exec_argv(self, argv, *, cwd=None, timeout_seconds=10):
        _ = argv, cwd, timeout_seconds
        return self.result


def _caps(*, exec_allowed: bool = True, git_available: bool = True) -> HostCapabilities:
    return HostCapabilities(
        cwd_trust="trusted",
        fs_read_commands_home=True,
        fs_write_config_root=True,
        fs_write_commands_home=True,
        fs_write_workspaces_home=True,
        fs_write_repo_root=True,
        exec_allowed=exec_allowed,
        git_available=git_available,
    )


@pytest.mark.governance
def test_resolver_uses_git_toplevel_from_highest_priority_env(tmp_path: Path):
    inv = tmp_path / "inv"
    inv.mkdir(parents=True, exist_ok=True)
    top = tmp_path / "repo"
    top.mkdir(parents=True, exist_ok=True)
    adapter = StubAdapter(
        env={"OPENCODE_REPO_ROOT": str(inv)},
        cwd_path=tmp_path,
        caps=_caps(),
        result=ExecResult(argv=("git",), cwd=str(inv), exit_code=0, stdout=str(top) + "\n", stderr=""),
    )

    result = resolve_repo_root(adapter=adapter, cwd=tmp_path)

    assert result.repo_root == top.resolve()
    assert result.is_git_root is True
    assert result.reason_code == "none"
    assert result.source.endswith("git-rev-parse")


@pytest.mark.governance
def test_resolver_blocks_when_git_exec_fails(tmp_path: Path):
    adapter = StubAdapter(
        env={},
        cwd_path=tmp_path,
        caps=_caps(),
        result=ExecResult(argv=("git",), cwd=str(tmp_path), exit_code=128, stdout="", stderr="not a git repo"),
    )

    result = resolve_repo_root(adapter=adapter, cwd=tmp_path)

    assert result.repo_root is None
    assert result.is_git_root is False
    assert result.reason_code == "BLOCKED-REPO-IDENTITY-RESOLUTION"


@pytest.mark.governance
def test_resolver_blocks_when_exec_disallowed(tmp_path: Path):
    adapter = StubAdapter(
        env={},
        cwd_path=tmp_path,
        caps=_caps(exec_allowed=False),
        result=ExecResult(argv=("git",), cwd=str(tmp_path), exit_code=0, stdout="", stderr=""),
    )

    result = resolve_repo_root(adapter=adapter, cwd=tmp_path)

    assert result.repo_root is None
    assert result.reason_code == "BLOCKED-EXEC-DISALLOWED"
