from __future__ import annotations

import importlib.util
import json
import platform
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "diagnostics" / "start_preflight_persistence.py"
    spec = importlib.util.spec_from_file_location("start_preflight_persistence", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_persistence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_emit_preflight_treats_python3_as_python_equivalent(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Preflight should not block when python3 exists but python alias is missing."""

    module = _load_module()
    monkeypatch.setattr(module, "TOOL_CATALOG", REPO_ROOT / "diagnostics" / "tool_requirements.json")

    def fake_which(command: str):
        if command == "git":
            return "/usr/bin/git"
        if command == "python3":
            return "/usr/bin/python3"
        if command == "python":
            return None
        return None

    monkeypatch.setattr(module.shutil, "which", fake_which)
    monkeypatch.setattr(module, "BINDING_OK", True)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {
            "required_now": [
                {"command": "git"},
                {"command": "python"},
                {"command": "python3"},
            ],
            "required_later": [],
        },
    )

    module.emit_preflight()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert payload["preflight"] == "ok"
    assert payload["block_now"] is False
    assert payload["missing"] == []
    assert "python" in payload["available"]
    assert "python3" in payload["available"]
    assert "windows_longpaths" in payload
    assert "git_safe_directory" in payload
    assert "advisories" in payload


@pytest.mark.governance
def test_emit_preflight_blocks_when_both_python_aliases_missing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Preflight should block when neither python nor python3 is available."""

    module = _load_module()
    monkeypatch.setattr(module, "TOOL_CATALOG", REPO_ROOT / "diagnostics" / "tool_requirements.json")

    def fake_which(command: str):
        if command == "git":
            return "/usr/bin/git"
        return None

    monkeypatch.setattr(module.shutil, "which", fake_which)
    monkeypatch.setattr(module, "BINDING_OK", True)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {
            "required_now": [
                {"command": "git"},
                {"command": "python"},
                {"command": "python3"},
            ],
            "required_later": [],
        },
    )

    module.emit_preflight()
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert payload["preflight"] == "degraded"
    assert payload["block_now"] is True
    assert set(payload["missing"]) == {"python", "python3"}
    assert "windows_longpaths" in payload
    assert "git_safe_directory" in payload


@pytest.mark.governance
def test_emit_preflight_blocks_on_invalid_binding_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    module = _load_module()
    monkeypatch.setattr(module, "BINDING_OK", False)
    monkeypatch.setattr(
        module,
        "load_json",
        lambda _path: {
            "required_now": [{"command": "git"}],
            "required_later": [],
        },
    )
    monkeypatch.setattr(module.shutil, "which", lambda _c: "/usr/bin/git")

    module.emit_preflight()
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["binding_evidence"] == "invalid"
    assert payload["block_now"] is True


@pytest.mark.governance
def test_preflight_discovers_binding_from_cwd_ancestor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / "commands"
    cfg.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "configRoot": str(tmp_path),
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    nested = tmp_path / "repo" / "a" / "b"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))

    module = _load_module()
    assert module.BINDING_OK is False


@pytest.mark.governance
def test_preflight_discovers_binding_from_cwd_ancestor_with_dev_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cfg = tmp_path / "commands"
    cfg.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "configRoot": str(tmp_path),
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    nested = tmp_path / "repo" / "a" / "b"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setenv("OPENCODE_ALLOW_CWD_BINDINGS", "1")

    module = _load_module()
    assert module.BINDING_OK is True


@pytest.mark.governance
def test_preflight_discovers_binding_from_canonical_home_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / ".config" / "opencode"
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(cfg / "commands"),
            "workspacesHome": str(cfg / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (cfg / "commands").mkdir(parents=True, exist_ok=True)
    (cfg / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)

    module = _load_module()
    assert module.BINDING_OK is True


@pytest.mark.governance
def test_preflight_discovers_binding_from_canonical_home_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / ".config" / "opencode"
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(cfg / "commands"),
            "workspacesHome": str(cfg / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (cfg / "commands").mkdir(parents=True, exist_ok=True)
    (cfg / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(tmp_path)

    module = _load_module()
    assert module.BINDING_OK is True
