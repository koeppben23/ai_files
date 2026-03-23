from __future__ import annotations

from governance_runtime.entrypoints.command_profiles import render_command_profiles


def test_command_profiles_preserve_argv_with_spaces():
    argv = ["py -3", "governance_runtime/entrypoints/persist_workspace_artifacts.py", "--config-root", "C:/My Folder/opencode"]
    profiles = render_command_profiles(argv)

    assert profiles["argv"] == argv
    assert "C:/My Folder/opencode" in profiles["bash"]
    assert '"C:/My Folder/opencode"' in profiles["cmd"]
    assert '"C:/My Folder/opencode"' in profiles["powershell"]
