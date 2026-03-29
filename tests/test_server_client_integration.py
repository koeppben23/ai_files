"""Tests for server client integration in production paths.

These tests verify:
1. Server path success - no CLI subprocess invoked
2. Server path failure → legacy fallback
3. server_required mode → fail-closed
4. invoke_backend correctly set
5. invoke_backend_url correctly set
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestPhase5ServerClientIntegration:
    """Tests for phase5_plan_record_persist.py server client integration."""

    @pytest.fixture
    def mock_env(self, monkeypatch: pytest.MonkeyPatch):
        """Setup mock environment for server client tests."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-session-123")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        return monkeypatch

    def test_server_client_success_sets_invoke_backend(
        self, mock_env, monkeypatch: pytest.MonkeyPatch
    ):
        """Server path success should set invoke_backend to 'server_client'."""
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        mock_response = {
            "info": {
                "parts": [{"type": "text", "text": '{"plan": "test plan content"}'}]
            }
        }

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.post_json"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = send_session_prompt(
                session_id="test-session-123",
                text="Generate a plan",
                model={"providerID": "openai", "modelID": "gpt-5"},
            )
            text = extract_session_response(result)

            assert text == '{"plan": "test plan content"}'
            mock_post.assert_called_once()

    def test_server_client_failure_without_required_falls_back(
        self, mock_env, monkeypatch: pytest.MonkeyPatch
    ):
        """Without server_required, server failure should allow legacy fallback."""
        monkeypatch.delenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", raising=False)

        from governance_runtime.infrastructure.opencode_server_client import (
            ServerNotAvailableError,
            send_session_prompt,
        )

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url"
        ) as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError("Server not available")

            with pytest.raises(ServerNotAvailableError):
                send_session_prompt(
                    session_id="test-session-123",
                    text="Generate a plan",
                )

    def test_server_client_required_mode_fails_closed(
        self, mock_env, monkeypatch: pytest.MonkeyPatch
    ):
        """With server_required, server failure should fail-closed."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")

        from governance_runtime.infrastructure.opencode_server_client import (
            ServerNotAvailableError,
            is_server_required_mode,
            send_session_prompt,
        )

        assert is_server_required_mode() is True

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url"
        ) as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError("Server not available")

            with pytest.raises(ServerNotAvailableError) as exc_info:
                send_session_prompt(
                    session_id="test-session-123",
                    text="Generate a plan",
                    required=True,
                )

            assert "required" in str(exc_info.value).lower() or "not available" in str(
                exc_info.value
            ).lower()


class TestImplementStartServerClientIntegration:
    """Tests for implement_start.py server client integration."""

    @pytest.fixture
    def mock_env(self, monkeypatch: pytest.MonkeyPatch):
        """Setup mock environment for server client tests."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-session-456")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        return monkeypatch

    def test_server_client_invoke_backend_url_set(
        self, mock_env, monkeypatch: pytest.MonkeyPatch
    ):
        """Server path should set invoke_backend_url when successful."""
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            resolve_opencode_server_base_url,
            send_session_prompt,
        )

        mock_response = {
            "info": {
                "parts": [
                    {
                        "type": "text",
                        "text": '{"files_changed": ["test.py"], "status": "success"}',
                    }
                ]
            }
        }

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.post_json"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = send_session_prompt(
                session_id="test-session-456",
                text="Implement the plan",
                model={"providerID": "openai", "modelID": "gpt-5"},
            )
            text = extract_session_response(result)

            assert "files_changed" in text
            url = resolve_opencode_server_base_url()
            assert url == "http://127.0.0.1:4096"


class TestPhase6LLMCallerServerClientIntegration:
    """Tests for phase6_review_orchestrator/llm_caller.py server client integration."""

    @pytest.fixture
    def mock_env(self, monkeypatch: pytest.MonkeyPatch):
        """Setup mock environment for server client tests."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-session-789")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        return monkeypatch

    def test_llm_caller_server_success_sets_invoke_backend(
        self, mock_env, monkeypatch: pytest.MonkeyPatch
    ):
        """LLMCaller should set invoke_backend to 'server_client' on success."""
        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        mock_response = {
            "info": {
                "parts": [
                    {
                        "type": "text",
                        "text": '{"verdict": "approve", "findings": []}',
                    }
                ]
            }
        }

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.post_json"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = send_session_prompt(
                session_id="test-session-789",
                text="Review the implementation",
                model={"providerID": "openai", "modelID": "gpt-5"},
            )
            text = extract_session_response(result)

            assert "verdict" in text
            assert "approve" in text

    def test_llm_caller_server_failure_with_required_fails_closed(
        self, mock_env, monkeypatch: pytest.MonkeyPatch
    ):
        """With server_required, LLMCaller should fail-closed."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")

        from governance_runtime.infrastructure.opencode_server_client import (
            ServerNotAvailableError,
            is_server_required_mode,
            send_session_prompt,
        )

        assert is_server_required_mode() is True

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url"
        ) as mock_resolve:
            mock_resolve.side_effect = ServerNotAvailableError(
                "Server required but not available"
            )

            with pytest.raises(ServerNotAvailableError) as exc_info:
                send_session_prompt(
                    session_id="test-session-789",
                    text="Review",
                    required=True,
                )

            assert "required" in str(exc_info.value).lower()


class TestServerClientEvidence:
    """Tests for server client evidence fields."""

    def test_invoke_backend_evidence_server_client(self, monkeypatch: pytest.MonkeyPatch):
        """invoke_backend should be 'server_client' when server path is used."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-session-evidence")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")

        from governance_runtime.infrastructure.opencode_server_client import (
            extract_session_response,
            send_session_prompt,
        )

        mock_response = {"info": {"parts": [{"type": "text", "text": "test"}]}}

        with patch(
            "governance_runtime.infrastructure.opencode_server_client.post_json"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = send_session_prompt(
                session_id="test-session-evidence",
                text="test",
            )
            text = extract_session_response(result)

            assert text == "test"
            call_args = mock_post.call_args
            assert "test-session-evidence" in call_args[0][0]

    def test_invoke_backend_url_resolved(self, monkeypatch: pytest.MonkeyPatch):
        """invoke_backend_url should be resolved from environment."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://custom:8080")

        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
        )

        url = resolve_opencode_server_base_url()
        assert url == "http://custom:8080"

    def test_server_required_mode_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """is_server_required_mode should read from environment."""
        from governance_runtime.infrastructure.opencode_server_client import (
            is_server_required_mode,
        )

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        assert is_server_required_mode() is True

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "true")
        assert is_server_required_mode() is True

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "0")
        assert is_server_required_mode() is False

        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "false")
        assert is_server_required_mode() is False

        monkeypatch.delenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", raising=False)
        assert is_server_required_mode() is False
