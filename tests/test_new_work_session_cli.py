from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

from governance.entrypoints import new_work_session

from .test_new_work_session_entrypoint import _setup_workspace


def _load_script_module() -> object:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "governance_session_new.py"
    spec = spec_from_file_location("governance_session_new", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_plugin_module() -> object:
    plugin_path = Path(__file__).resolve().parents[1] / ".opencode" / "plugins" / "new_work_session_plugin.py"
    spec = spec_from_file_location("new_work_session_plugin", plugin_path)
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
        assert state["Next"] == "5"

    # -- Bad --
    def test_script_wrapper_forwards_failure_exit_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_root = tmp_path / "cfg"
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        script_mod = _load_script_module()

        monkeypatch.setattr("sys.argv", ["governance_session_new.py", "--quiet"])
        code = script_mod.main()
        assert code == 2

    # -- Edge --
    def test_plugin_and_cli_paths_produce_same_target_phase(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        cli_root = tmp_path / "cli"
        plugin_root = tmp_path / "plugin"
        cli_config, cli_state_path, _ = _setup_workspace(cli_root)
        plugin_config, plugin_state_path, _ = _setup_workspace(plugin_root)

        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(cli_config))
        assert new_work_session.main(["--trigger-source", "cli", "--session-id", "sess-cli", "--quiet"]) == 0
        _ = capsys.readouterr().out
        cli_state = json.loads(cli_state_path.read_text(encoding="utf-8"))["SESSION_STATE"]

        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(plugin_config))
        plugin = _load_plugin_module()
        plugin.reset_seen_sessions_for_tests()

        def runner(argv: list[str], _cwd: str | None) -> SimpleNamespace:
            assert argv[1:3] == ["-m", "governance.entrypoints.new_work_session"]
            rc = new_work_session.main(argv[3:])
            return SimpleNamespace(returncode=rc, stderr="")

        result = plugin.handle_event(
            {"type": "session.created", "session_id": "sess-plugin", "repo_root": "/tmp/repo"},
            run_command=runner,
            logger=lambda *_args, **_kwargs: None,
            python_command="python3",
        )
        assert result["status"] == "ok"
        _ = capsys.readouterr().out
        plugin_state = json.loads(plugin_state_path.read_text(encoding="utf-8"))["SESSION_STATE"]

        assert cli_state["Phase"] == plugin_state["Phase"] == "4"
        assert cli_state["Next"] == plugin_state["Next"] == "5"
        assert cli_state["Ticket"] == plugin_state["Ticket"] is None
        assert cli_state["Task"] == plugin_state["Task"] is None

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
