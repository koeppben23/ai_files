from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import pytest

from governance_runtime.entrypoints import new_work_session

from .test_new_work_session_entrypoint import _setup_workspace


def _load_script_module() -> Any:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "governance_session_new.py"
    spec = spec_from_file_location("governance_session_new", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class TestNewWorkSessionCliPath:
    # -- Good --
    def test_module_cli_initializes_phase4(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))

        code = new_work_session.main(["--trigger-source", "pipeline", "--quiet"])
        assert code == 0
        _ = json.loads(capsys.readouterr().out.strip())

        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["Phase"] == "4"
        assert state["Next"] == "4"

    # -- Bad --
    def test_script_wrapper_forwards_failure_exit_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_root = tmp_path / "cfg"
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        script_mod = _load_script_module()

        monkeypatch.setattr("sys.argv", ["governance_session_new.py", "--quiet"])
        code = script_mod.main()
        assert code == 2

    # -- Edge --
    def test_desktop_and_cli_trigger_sources_produce_same_target_phase(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        cli_root = tmp_path / "cli"
        desktop_root = tmp_path / "desktop"
        cli_config, cli_state_path, _ = _setup_workspace(cli_root)
        desktop_config, desktop_state_path, _ = _setup_workspace(desktop_root)

        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cli_config))
        assert new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-cli", "--quiet"]) == 0
        _ = capsys.readouterr().out
        cli_state = json.loads(cli_state_path.read_text(encoding="utf-8"))["SESSION_STATE"]

        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(desktop_config))
        assert new_work_session.main(["--trigger-source", "desktop-plugin", "--session-id", "sess-plugin", "--quiet"]) == 0
        _ = capsys.readouterr().out
        desktop_state = json.loads(desktop_state_path.read_text(encoding="utf-8"))["SESSION_STATE"]

        assert cli_state["Phase"] == desktop_state["Phase"] == "4"
        assert cli_state["Next"] == desktop_state["Next"] == "4"
        assert cli_state["Ticket"] == desktop_state["Ticket"] is None
        assert cli_state["Task"] == desktop_state["Task"] is None

    # -- Corner --
    def test_script_wrapper_passes_trigger_source_argument(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        config_root, session_path, _ = _setup_workspace(tmp_path)
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        script_mod = _load_script_module()

        monkeypatch.setattr("sys.argv", ["governance_session_new.py", "--trigger-source", "pipeline", "--quiet"])
        code = script_mod.main()
        assert code == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] in {"new-work-session-created", "new-work-session-deduped"}

        events = (session_path.parent / "events.jsonl").read_text(encoding="utf-8")
        assert "\"trigger_source\":\"pipeline\"" in events
