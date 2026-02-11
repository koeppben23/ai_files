from __future__ import annotations

import pytest

from governance.engine.adapters import LocalHostAdapter, OpenCodeDesktopAdapter


@pytest.mark.governance
def test_local_host_adapter_defaults_to_trusted_cwd_and_git_available():
    """Local adapter should keep conservative CLI defaults for existing flows."""

    caps = LocalHostAdapter().capabilities()
    assert caps.cwd_trust == "trusted"
    assert caps.fs_read is True
    assert caps.git_available is True


@pytest.mark.governance
def test_desktop_adapter_defaults_to_untrusted_cwd(monkeypatch: pytest.MonkeyPatch):
    """Desktop adapter should treat cwd as untrusted by default."""

    monkeypatch.delenv("OPENCODE_DISABLE_GIT", raising=False)
    caps = OpenCodeDesktopAdapter(git_available_override=True).capabilities()
    assert caps.cwd_trust == "untrusted"
    assert caps.fs_read is True
    assert caps.git_available is True


@pytest.mark.governance
def test_desktop_adapter_respects_disable_git_env(monkeypatch: pytest.MonkeyPatch):
    """Desktop adapter should conservatively disable git when env requests it."""

    monkeypatch.setenv("OPENCODE_DISABLE_GIT", "1")
    caps = OpenCodeDesktopAdapter(git_available_override=None).capabilities()
    assert caps.git_available is False
