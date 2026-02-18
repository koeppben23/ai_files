from __future__ import annotations

from pathlib import Path

import pytest

from governance.engine.adapters import LocalHostAdapter, OpenCodeDesktopAdapter


@pytest.mark.governance
def test_local_host_adapter_defaults_to_trusted_cwd_and_git_available():
    """Local adapter should keep conservative CLI defaults for existing flows."""

    caps = LocalHostAdapter().capabilities()
    assert caps.cwd_trust == "trusted"
    assert caps.fs_read_commands_home in {True, False}
    assert caps.fs_write_workspaces_home in {True, False}
    assert caps.exec_allowed in {True, False}
    assert caps.git_available is True
    assert isinstance(caps.stable_hash(), str) and len(caps.stable_hash()) == 16
    assert LocalHostAdapter().default_operating_mode() == "user"


@pytest.mark.governance
def test_desktop_adapter_defaults_to_untrusted_cwd(monkeypatch: pytest.MonkeyPatch):
    """Desktop adapter should treat cwd as untrusted by default."""

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("OPENCODE_DISABLE_GIT", raising=False)
    caps = OpenCodeDesktopAdapter(git_available_override=True).capabilities()
    assert caps.cwd_trust == "untrusted"
    assert caps.fs_read_commands_home in {True, False}
    assert caps.git_available is True
    assert OpenCodeDesktopAdapter(git_available_override=True).default_operating_mode() == "user"


@pytest.mark.governance
def test_desktop_adapter_respects_disable_git_env(monkeypatch: pytest.MonkeyPatch):
    """Desktop adapter should conservatively disable git when env requests it."""

    monkeypatch.setenv("OPENCODE_DISABLE_GIT", "1")
    caps = OpenCodeDesktopAdapter(git_available_override=None).capabilities()
    assert caps.git_available is False


@pytest.mark.governance
def test_desktop_adapter_defaults_to_pipeline_mode_in_ci(monkeypatch: pytest.MonkeyPatch):
    """Desktop adapter should switch default operating mode in CI environments."""

    monkeypatch.setenv("CI", "true")
    assert OpenCodeDesktopAdapter().default_operating_mode() == "pipeline"


@pytest.mark.governance
def test_local_adapter_fs_write_repo_root_requires_absolute_env_binding(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("OPENCODE_REPO_ROOT", raising=False)
    no_env_caps = LocalHostAdapter().capabilities()
    assert no_env_caps.fs_write_repo_root is False

    monkeypatch.setenv("OPENCODE_REPO_ROOT", "relative/path")
    relative_caps = LocalHostAdapter().capabilities()
    assert relative_caps.fs_write_repo_root is False

    repo_root = tmp_path / "repo-root"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(repo_root))
    absolute_caps = LocalHostAdapter().capabilities()
    assert absolute_caps.fs_write_repo_root is True
