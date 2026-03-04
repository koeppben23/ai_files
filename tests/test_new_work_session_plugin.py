from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_plugin_module() -> Any:
    plugin_path = Path(__file__).resolve().parents[1] / ".opencode" / "plugins" / "new_work_session_plugin.py"
    spec = spec_from_file_location("new_work_session_plugin", plugin_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNewWorkSessionPlugin:
    # -- Good --
    def test_session_created_triggers_initializer_once(self) -> None:
        module = _load_plugin_module()
        module.reset_seen_sessions_for_tests()
        calls: list[list[str]] = []

        def runner(argv: list[str], _cwd: str | None) -> SimpleNamespace:
            calls.append(argv)
            return SimpleNamespace(returncode=0, stderr="")

        result = module.handle_event(
            {"type": "session.created", "session_id": "sess-101", "repo_root": "/tmp/repo"},
            run_command=runner,
            logger=lambda *_args, **_kwargs: None,
            python_command="python3",
        )

        assert result["status"] == "ok"
        assert len(calls) == 1
        assert calls[0][:3] == ["python3", "-m", "governance.entrypoints.new_work_session"]

    # -- Bad --
    def test_ignores_non_session_created_events(self) -> None:
        module = _load_plugin_module()
        module.reset_seen_sessions_for_tests()

        called = False

        def runner(_argv: list[str], _cwd: str | None) -> SimpleNamespace:
            nonlocal called
            called = True
            return SimpleNamespace(returncode=0, stderr="")

        result = module.handle_event(
            {"type": "session.closed", "session_id": "sess-102", "repo_root": "/tmp/repo"},
            run_command=runner,
            logger=lambda *_args, **_kwargs: None,
        )

        assert result["status"] == "ignored"
        assert called is False

    # -- Edge --
    def test_dedupes_same_session_id(self) -> None:
        module = _load_plugin_module()
        module.reset_seen_sessions_for_tests()
        count = 0

        def runner(_argv: list[str], _cwd: str | None) -> SimpleNamespace:
            nonlocal count
            count += 1
            return SimpleNamespace(returncode=0, stderr="")

        first = module.handle_event(
            {"type": "session.created", "session_id": "sess-103", "repo_root": "/tmp/repo"},
            run_command=runner,
            logger=lambda *_args, **_kwargs: None,
        )
        second = module.handle_event(
            {"type": "session.created", "session_id": "sess-103", "repo_root": "/tmp/repo"},
            run_command=runner,
            logger=lambda *_args, **_kwargs: None,
        )

        assert first["status"] == "ok"
        assert second["status"] == "ignored"
        assert second["reason"] == "already-processed"
        assert count == 1

    # -- Corner --
    def test_spawn_failure_is_logged_and_non_blocking(self) -> None:
        module = _load_plugin_module()
        module.reset_seen_sessions_for_tests()
        logs: list[tuple[str, str]] = []

        def failing_runner(_argv: list[str], _cwd: str | None) -> SimpleNamespace:
            raise RuntimeError("boom")

        def logger(level: str, message: str) -> None:
            logs.append((level, message))

        result = module.handle_event(
            {"type": "session.created", "session_id": "sess-104", "repo_root": "/tmp/repo"},
            run_command=failing_runner,
            logger=logger,
        )

        assert result["status"] == "error"
        assert result["reason"] == "spawn-failed"
        assert logs and logs[0][0] == "error"
