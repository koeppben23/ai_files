"""Direct tests for production paths using server client."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


class TestPhase5PlanRecordPersistServerClient:
    """Direct tests for phase5_plan_record_persist.py server client path."""

    @pytest.fixture
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        return monkeypatch

    def test_phase5_plan_generation_server_success(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        plan_data = {"plan_summary": "Test plan", "plan_body": "Test body", "version": 1}
        mock_response = {"info": {"parts": [{"type": "text", "text": json.dumps(plan_data)}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            result = send_session_prompt("phase5-test-session", "Generate a plan",
                                          model={"providerID": "openai", "modelID": "gpt-5"})
            text = extract_session_response(result)
            parsed = json.loads(text)
            assert parsed["plan_summary"] == "Test plan"

    def test_phase5_review_server_success(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        review_data = {"verdict": "approve", "findings": [], "review_summary": "Looks good"}
        mock_response = {"info": {"parts": [{"type": "text", "text": json.dumps(review_data)}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            result = send_session_prompt("phase5-test-session", "Review this plan",
                                          model={"providerID": "openai", "modelID": "gpt-5"})
            text = extract_session_response(result)
            parsed = json.loads(text)
            assert parsed["verdict"] == "approve"

    def test_phase5_server_required_fail_closed(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            ServerNotAvailableError,
            is_server_required_mode,
            send_session_prompt,
        )

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        assert is_server_required_mode() is True

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError("Server required but not available")
            with pytest.raises(ServerNotAvailableError) as exc_info:
                send_session_prompt("phase5-test-session", "Generate a plan", required=True)
            assert "required" in str(exc_info.value).lower()


class TestImplementStartServerClient:
    """Direct tests for implement_start.py server client path."""

    @pytest.fixture
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "implement-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        return monkeypatch

    def test_implement_server_success_with_changes(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        impl_data = {"status": "success", "files_changed": ["test.py", "main.py"]}
        mock_response = {"info": {"parts": [{"type": "text", "text": json.dumps(impl_data)}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            result = send_session_prompt("implement-test-session", "Implement the plan",
                                          model={"providerID": "openai", "modelID": "gpt-5"})
            text = extract_session_response(result)
            parsed = json.loads(text)
            assert parsed["status"] == "success"
            assert "test.py" in parsed["files_changed"]

    def test_implement_valid_output_no_changes(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        impl_data = {"status": "success", "files_changed": []}
        mock_response = {"info": {"parts": [{"type": "text", "text": json.dumps(impl_data)}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            result = send_session_prompt("implement-test-session", "Implement the plan",
                                          model={"providerID": "openai", "modelID": "gpt-5"})
            text = extract_session_response(result)
            parsed = json.loads(text)
            assert parsed["files_changed"] == []

    def test_implement_server_required_fail_closed(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            ServerNotAvailableError,
            is_server_required_mode,
            send_session_prompt,
        )

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        assert is_server_required_mode() is True

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError("Server required but not available")
            with pytest.raises(ServerNotAvailableError) as exc_info:
                send_session_prompt("implement-test-session", "Implement the plan", required=True)
            assert "required" in str(exc_info.value).lower()


class TestPhase6LLMCallerServerClient:
    """Direct tests for phase6_review_orchestrator/llm_caller.py."""

    @pytest.fixture
    def setup_env(self, monkeypatch):
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase6-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        return monkeypatch

    def test_phase6_server_success_approve(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        review_data = {"verdict": "approve", "findings": []}
        mock_response = {"info": {"parts": [{"type": "text", "text": json.dumps(review_data)}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            result = send_session_prompt("phase6-test-session", "Review implementation",
                                          model={"providerID": "openai", "modelID": "gpt-5"})
            text = extract_session_response(result)
            parsed = json.loads(text)
            assert parsed["verdict"] == "approve"

    def test_phase6_invalid_server_response(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        mock_response = {"info": {"parts": [{"type": "text", "text": "Not valid JSON"}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            result = send_session_prompt("phase6-test-session", "Review implementation",
                                          model={"providerID": "openai", "modelID": "gpt-5"})
            text = extract_session_response(result)
            with pytest.raises(json.JSONDecodeError):
                json.loads(text)

    def test_phase6_server_required_fail_closed(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import (
            ServerNotAvailableError,
            is_server_required_mode,
            send_session_prompt,
        )

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        assert is_server_required_mode() is True

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError("Server required but not available")
            with pytest.raises(ServerNotAvailableError) as exc_info:
                send_session_prompt("phase6-test-session", "Review", required=True)
            assert "required" in str(exc_info.value).lower()

    def test_phase6_server_required_blocks_legacy(self, setup_env, monkeypatch):
        from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        from governance_runtime.infrastructure.opencode_server_client import is_server_required_mode
        assert is_server_required_mode() is True

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError("Server required but not available")
            from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
            with pytest.raises(ServerNotAvailableError):
                send_session_prompt("phase6-test-session", "Review", required=True)


class TestServerClientUsesHTTP:
    """Verify server client uses HTTP, not subprocess."""

    def test_server_client_uses_post_json(self, monkeypatch):
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        from governance_runtime.infrastructure.opencode_server_client import send_session_prompt

        result_data = {"result": "ok"}
        mock_response = {"info": {"parts": [{"type": "text", "text": json.dumps(result_data)}]}}

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = mock_response
            send_session_prompt("test-session", "test")
            mock_post.assert_called_once()
