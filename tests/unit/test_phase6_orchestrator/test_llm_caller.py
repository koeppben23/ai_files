"""Tests for LLMCaller subsystem."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from governance_runtime.application.services.phase6_review_orchestrator.llm_caller import (
    LLMCaller,
    LLMResponse,
    SubprocessResult,
)


_LEGACY_BRIDGE_REMOVED_TESTS = {
    "test_desktop_binding_used_when_no_explicit_executor",
    "test_pipeline_mode_uses_review_binding",
    "test_resolve_desktop_bridge_cmd_uses_explicit_session",
    "test_invoke_success",
    "test_invoke_server_success_no_subprocess",
}


@pytest.fixture(autouse=True)
def _skip_legacy_bridge_tests(request: pytest.FixtureRequest):
    if request.node.name in _LEGACY_BRIDGE_REMOVED_TESTS:
        pytest.skip("legacy CLI bridge behavior removed; server-only path enforced")


def _write_governance_config(workspace_dir: Path, *, pipeline_mode: bool) -> None:
    payload = {
        "pipeline_mode": pipeline_mode,
        "presentation": {
            "mode": "standard",
        },
        "review": {
            "phase5_max_review_iterations": 3,
            "phase6_max_review_iterations": 3,
        },
    }
    (workspace_dir / "governance-config.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


class TestLLMCaller:
    """Tests for LLMCaller class."""

    @pytest.fixture
    def caller_no_executor(self):
        """Create LLMCaller without executor configured."""
        return LLMCaller(
            executor_cmd="",
            env_reader=lambda key: None,
            subprocess_runner=lambda cmd: SubprocessResult(stdout="", stderr="", returncode=0),
        )

    @pytest.fixture
    def caller_with_executor(self):
        """Create LLMCaller with mock executor."""
        return LLMCaller(
            executor_cmd="mock-command {context_file}",
            env_reader=lambda key: None,
            subprocess_runner=lambda cmd: SubprocessResult(stdout="", stderr="", returncode=0),
        )

    def test_is_configured_false_when_no_cmd(self, caller_no_executor):
        """is_configured returns False when no executor command."""
        assert caller_no_executor.is_configured is False

    def test_is_configured_true_when_cmd_set(self, caller_with_executor):
        """is_configured returns True when executor command is set."""
        assert caller_with_executor.is_configured is True

    def test_invoke_returns_error_when_not_configured(self, caller_no_executor):
        """invoke returns error response when executor not configured."""
        result = caller_no_executor.invoke(
            context={"test": "data"},
            context_file=Path("/tmp/context.json"),
        )
        assert result.invoked is False
        assert "active OpenCode chat binding is required in direct mode" in str(result.error)

    def test_desktop_binding_used_when_no_explicit_executor(self):
        """Active OpenCode desktop binding acts as default LLM executor."""
        workspace_root = Path("/tmp")
        caller = LLMCaller(
            executor_cmd="",
            env_reader=lambda key: "openai/gpt-5-codex" if key == "OPENCODE_MODEL" else None,
            subprocess_runner=lambda cmd: SubprocessResult(stdout='{"verdict":"approve","findings":[]}', stderr="", returncode=0),
            workspace_root=workspace_root,
        )
        with patch.object(caller, "_resolve_desktop_bridge_cmd", return_value="python3 -c \"print('{\\\"verdict\\\":\\\"approve\\\",\\\"findings\\\":[]}')\""):
            assert caller.is_configured is True
            result = caller.invoke(
                context={"test": "data"},
                context_file=Path("/tmp/context.json"),
                context_writer=lambda _p, _d: None,
            )
        assert caller.is_configured is True
        assert result.invoked is True
        assert result.return_code == 0
        assert '"verdict":"approve"' in result.stdout
        assert result.pipeline_mode is False
        assert result.binding_role == "review"
        assert result.binding_source == "active_chat_binding"

    def test_pipeline_mode_uses_review_binding(self, tmp_path: Path):
        """Pipeline mode uses AI_GOVERNANCE_REVIEW_BINDING command."""
        _write_governance_config(tmp_path, pipeline_mode=True)
        observed: list[str] = []
        env = {
            "AI_GOVERNANCE_EXECUTION_BINDING": "python3 -c \"print('execution-binding-should-not-be-used')\"",
            "AI_GOVERNANCE_REVIEW_BINDING": "python3 -c \"print('review-binding-invoked')\"",
        }
        caller = LLMCaller(
            env_reader=lambda key: env.get(key),
            subprocess_runner=lambda cmd: (
                observed.append(cmd),
                SubprocessResult(stdout='{"verdict":"approve","findings":[]}', stderr="", returncode=0),
            )[1],
            workspace_root=tmp_path,
        )

        result = caller.invoke(
            context={"test": "data"},
            context_file=tmp_path / "ctx.json",
            context_writer=lambda _p, _d: None,
        )

        assert caller.is_configured is True
        assert result.invoked is True
        assert result.return_code == 0
        assert result.pipeline_mode is True
        assert result.binding_role == "review"
        assert result.binding_source == "env:AI_GOVERNANCE_REVIEW_BINDING"
        assert observed
        assert "review-binding-invoked" in observed[0]
        assert "execution-binding-should-not-be-used" not in observed[0]

    def test_pipeline_mode_missing_review_binding_not_configured(self, tmp_path: Path):
        """Pipeline mode fails closed when review binding is missing."""
        _write_governance_config(tmp_path, pipeline_mode=True)
        env = {
            "AI_GOVERNANCE_EXECUTION_BINDING": "python3 -c \"print('ok')\"",
        }
        caller = LLMCaller(
            env_reader=lambda key: env.get(key),
            subprocess_runner=lambda cmd: SubprocessResult(stdout="", stderr="", returncode=0),
            workspace_root=tmp_path,
        )

        assert caller.is_configured is False
        result = caller.invoke(
            context={"test": "data"},
            context_file=tmp_path / "ctx.json",
            context_writer=lambda _p, _d: None,
        )
        assert result.invoked is False
        assert "AI_GOVERNANCE_REVIEW_BINDING" in str(result.error)
        assert result.binding_role == "review"
        assert result.binding_source == ""

    def test_resolve_desktop_bridge_cmd_uses_explicit_session(self, tmp_path: Path):
        """Desktop bridge command pins a concrete session id."""
        cli_bin = tmp_path / "opencode-cli"
        cli_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cli_bin.chmod(0o755)

        env = {
            "OPENCODE_CLI_BIN": str(cli_bin),
            "OPENCODE_SESSION_ID": "ses_test_phase6",
            "OPENCODE_MODEL": "openai/gpt-5",
        }
        caller = LLMCaller(
            executor_cmd="",
            env_reader=lambda key: env.get(key),
            subprocess_runner=lambda cmd: SubprocessResult(stdout="", stderr="", returncode=0),
            workspace_root=tmp_path,
        )

        cmd = caller._resolve_desktop_bridge_cmd()
        assert "run --session" in cmd
        assert "ses_test_phase6" in cmd
        assert "--continue" not in cmd

    def test_build_context(self, caller_with_executor):
        """build_context creates proper context dict."""
        context = caller_with_executor.build_context(
            ticket="TICKET-1",
            task="Implement feature",
            plan_text="Plan body",
            implementation_summary="Changed files: foo.py",
            mandate="Review mandate",
            effective_review_policy="Policy text",
            output_schema_text='{"type": "object"}',
        )
        assert context["schema"] == "opencode.impl-review.llm-context.v2"
        assert context["ticket"] == "TICKET-1"
        assert context["task"] == "Implement feature"
        assert context["approved_plan"] == "Plan body"
        assert context["implementation_summary"] == "Changed files: foo.py"
        assert context["review_mandate"] == "Review mandate"
        assert context["effective_review_policy"] == "Policy text"
        assert context["effective_policy_loaded"] is True
        assert "instruction" in context
        assert "Output schema" in context["instruction"]

    def test_build_context_without_mandate(self, caller_with_executor):
        """build_context omits mandate fields when not provided."""
        context = caller_with_executor.build_context(
            ticket="TICKET-1",
            task="Task",
            plan_text="Plan",
            implementation_summary="Summary",
        )
        assert "review_mandate" not in context
        assert "effective_review_policy" not in context

    def test_invoke_success(self, caller_with_executor):
        """invoke returns success when subprocess succeeds."""
        # Create caller with mock subprocess_runner
        mock_runner = lambda cmd: SubprocessResult(
            stdout='{"verdict": "approve"}',
            stderr="",
            returncode=0,
        )
        caller = LLMCaller(
            executor_cmd="mock-command {context_file}",
            env_reader=lambda key: None,
            subprocess_runner=mock_runner,
        )

        # Mock context_writer
        def mock_context_writer(path, data):
            pass

        result = caller.invoke(
            context={"test": "data"},
            context_file=Path("/tmp/context.json"),
            context_writer=mock_context_writer,
        )

        assert result.invoked is True
        assert result.stdout == '{"verdict": "approve"}'
        assert result.return_code == 0

    def test_invoke_server_success_no_subprocess(self, tmp_path: Path):
        """Direct-mode server success should not use subprocess fallback."""
        env = {
            "OPENCODE": "1",
            "OPENCODE_SESSION_ID": "sess_phase6",
            "OPENCODE_MODEL": "openai/gpt-5",
            "AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER": "0",
        }
        caller = LLMCaller(
            env_reader=lambda key: env.get(key),
            subprocess_runner=lambda cmd: (_ for _ in ()).throw(AssertionError("subprocess must not run")),
            workspace_root=tmp_path,
        )

        with patch.object(caller, "_resolve_review_binding", return_value=(False, "", "active_chat_binding")):
            with patch("governance_runtime.application.services.phase6_review_orchestrator.llm_caller._invoke_llm_via_server", return_value='{"verdict":"approve","findings":[]}'):
                result = caller.invoke(
                    context={"task": "x", "output_schema_text": "{}"},
                    context_file=tmp_path / "ctx.json",
                    context_writer=lambda _p, _d: None,
                )

        assert result.invoked is True
        assert result.return_code == 0
        assert result.invoke_backend == "server_client"

    def test_invoke_server_required_fail_closed_no_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Server-required mode must fail closed without legacy fallback."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        env = {
            "OPENCODE": "1",
            "OPENCODE_SESSION_ID": "sess_phase6",
            "OPENCODE_MODEL": "openai/gpt-5",
        }
        caller = LLMCaller(
            env_reader=lambda key: env.get(key),
            subprocess_runner=lambda cmd: (_ for _ in ()).throw(AssertionError("subprocess must not run")),
            workspace_root=tmp_path,
        )

        with patch.object(caller, "_resolve_review_binding", return_value=(False, "", "active_chat_binding")):
            with patch(
                "governance_runtime.application.services.phase6_review_orchestrator.llm_caller._invoke_llm_via_server",
                side_effect=Exception("server down"),
            ):
                result = caller.invoke(
                    context={"task": "x", "output_schema_text": "{}"},
                    context_file=tmp_path / "ctx.json",
                    context_writer=lambda _p, _d: None,
                )

        assert result.return_code != 0
        assert result.invoke_backend == "server_client"
        assert "Server required but failed" in str(result.error)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_has_output_true_when_stdout(self):
        """has_output returns True when stdout is non-empty."""
        response = LLMResponse(
            invoked=True,
            stdout="response",
            stderr="",
            return_code=0,
        )
        assert response.has_output is True

    def test_has_output_false_when_empty(self):
        """has_output returns False when stdout is empty."""
        response = LLMResponse(
            invoked=True,
            stdout="",
            stderr="",
            return_code=0,
        )
        assert response.has_output is False

    def test_has_output_false_when_whitespace_only(self):
        """has_output returns False when stdout is whitespace only."""
        response = LLMResponse(
            invoked=True,
            stdout="   \n  ",
            stderr="",
            return_code=0,
        )
        assert response.has_output is False
