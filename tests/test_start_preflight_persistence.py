from __future__ import annotations

import importlib.util
import json

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
