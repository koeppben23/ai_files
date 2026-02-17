from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.engine.adapters import LocalHostAdapter, OpenCodeDesktopAdapter


def _write_binding(config_root: Path, *, commands_home: Path, workspaces_home: Path) -> None:
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
        },
    }
    (config_root / "commands").mkdir(parents=True, exist_ok=True)
    (config_root / "commands" / "governance.paths.json").write_text(
        json.dumps(payload, ensure_ascii=True), encoding="utf-8"
    )


@pytest.mark.governance
def test_local_adapter_prefers_bound_workspaces_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / "cfg"
    commands_home = tmp_path / "bound-commands"
    workspaces_home = tmp_path / "bound-workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    _write_binding(cfg, commands_home=commands_home, workspaces_home=workspaces_home)

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cfg))
    adapter = LocalHostAdapter()
    caps = adapter.capabilities()
    assert caps.fs_write_workspaces_home is True


@pytest.mark.governance
def test_desktop_adapter_prefers_bound_commands_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / "cfg"
    commands_home = tmp_path / "bound-commands"
    workspaces_home = tmp_path / "bound-workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    _write_binding(cfg, commands_home=commands_home, workspaces_home=workspaces_home)

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cfg))
    adapter = OpenCodeDesktopAdapter(git_available_override=True)
    caps = adapter.capabilities()
    assert caps.fs_read_commands_home is True


@pytest.mark.governance
def test_adapter_fails_closed_when_binding_file_is_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / "cfg"
    (cfg / "commands").mkdir(parents=True, exist_ok=True)
    (cfg / "commands" / "governance.paths.json").write_text("{not-json", encoding="utf-8")

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cfg))
    adapter = LocalHostAdapter()
    caps = adapter.capabilities()

    assert caps.fs_read_commands_home is False
    assert caps.fs_write_commands_home is False
    assert caps.fs_write_workspaces_home is False
