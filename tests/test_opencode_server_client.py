from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from governance_runtime.infrastructure.opencode_server_client import (
    APIError,
    AuthenticationError,
    ServerNotAvailableError,
    check_server_health,
    extract_session_response,
    post_json,
    resolve_opencode_server_base_url,
    send_session_command,
    send_session_prompt,
)


class TestResolveServerBaseUrl:
    """Tests for server URL resolution.

    Happy: Valid env vars produce correct URL
    Bad: Missing env vars raise error
    Corner: Edge cases in env var handling
    """

    def test_happy_override_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: AI_GOVERNANCE_OPENCODE_SERVER_URL produces exact URL."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://custom:8080")
        result = resolve_opencode_server_base_url()
        assert result == "http://custom:8080"

    def test_happy_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Trailing slash is stripped from override URL."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://custom:8080/")
        result = resolve_opencode_server_base_url()
        assert result == "http://custom:8080"

    def test_happy_opencode_port(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: OPENCODE_PORT produces correct localhost URL."""
        monkeypatch.delenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", raising=False)
        monkeypatch.setenv("OPENCODE_PORT", "5000")
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:5000"

    def test_happy_opencode_port_default_4096(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Default port 4096 when only override is empty."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "")
        monkeypatch.setenv("OPENCODE_PORT", "")
        with pytest.raises(ServerNotAvailableError):
            resolve_opencode_server_base_url()

    def test_bad_no_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Missing all env vars raises ServerNotAvailableError."""
        monkeypatch.delenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", raising=False)
        monkeypatch.delenv("OPENCODE_PORT", raising=False)
        with pytest.raises(ServerNotAvailableError) as exc_info:
            resolve_opencode_server_base_url()
        assert "not resolvable" in str(exc_info.value).lower()

    def test_corner_whitespace_only(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: Whitespace-only values are treated as empty."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "   ")
        monkeypatch.setenv("OPENCODE_PORT", "")
        with pytest.raises(ServerNotAvailableError):
            resolve_opencode_server_base_url()


class TestExtractSessionResponse:
    """Tests for extracting text from session responses.

    Happy: structured_output and parts are extracted correctly
    Bad: Empty/malformed payloads
    Corner: Mixed content types
    """

    def test_happy_structured_output_dict(self):
        """Happy: Structured output dict is JSON-serialized."""
        payload = {
            "info": {
                "structured_output": {
                    "objective": "Test",
                    "target_state": "Done"
                }
            }
        }
        result = extract_session_response(payload)
        assert "objective" in result
        assert "Test" in result

    def test_happy_structured_output_string(self):
        """Happy: Structured output string is returned as-is."""
        payload = {
            "info": {
                "structured_output": "Just a string"
            }
        }
        result = extract_session_response(payload)
        assert result == "Just a string"

    def test_happy_text_parts(self):
        """Happy: Text parts are concatenated."""
        payload = {
            "info": {
                "parts": [
                    {"type": "text", "text": "Line 1"},
                    {"type": "text", "text": "Line 2"},
                ]
            }
        }
        result = extract_session_response(payload)
        assert result == "Line 1\nLine 2"

    def test_happy_text_parts_with_non_text(self):
        """Happy: Non-text parts are ignored, text parts concatenated."""
        payload = {
            "info": {
                "parts": [
                    {"type": "text", "text": "Line 1"},
                    {"type": "image", "data": "abc123"},
                    {"type": "text", "text": "Line 2"},
                ]
            }
        }
        result = extract_session_response(payload)
        assert result == "Line 1\nLine 2"

    def test_happy_both_structured_and_parts_prefers_structured(self):
        """Happy: Structured output takes priority over parts."""
        payload = {
            "info": {
                "structured_output": {"key": "value"},
                "parts": [{"type": "text", "text": "parts text"}]
            }
        }
        result = extract_session_response(payload)
        assert "key" in result

    def test_bad_empty_payload(self):
        """Bad: Empty payload returns empty string."""
        result = extract_session_response({})
        assert result == ""

    def test_bad_none_payload(self):
        """Bad: None payload returns empty string."""
        result = extract_session_response(None)
        assert result == ""

    def test_bad_string_payload(self):
        """Bad: String payload returns empty string."""
        result = extract_session_response("not a dict")
        assert result == ""

    def test_bad_missing_info(self):
        """Bad: Missing info key returns empty string."""
        result = extract_session_response({"foo": "bar"})
        assert result == ""

    def test_bad_info_is_string(self):
        """Bad: info as string returns empty string."""
        result = extract_session_response({"info": "not a dict"})
        assert result == ""

    def test_corner_empty_parts(self):
        """Corner: Empty parts list returns empty string."""
        payload = {"info": {"parts": []}}
        result = extract_session_response(payload)
        assert result == ""

    def test_corner_parts_not_a_list(self):
        """Corner: parts as non-list returns empty string."""
        payload = {"info": {"parts": "not a list"}}
        result = extract_session_response(payload)
        assert result == ""

    def test_happy_top_level_parts(self):
        """Happy: Top-level parts are extracted when info.parts is empty."""
        payload = {
            "info": {},
            "parts": [
                {"type": "text", "text": "Top level 1"},
                {"type": "text", "text": "Top level 2"},
            ]
        }
        result = extract_session_response(payload)
        assert result == "Top level 1\nTop level 2"


class TestSendSessionPrompt:
    """Tests for sending prompts to sessions.

    Happy: Valid requests are sent correctly
    Bad: Invalid session_id, server errors
    Corner: Model and output_schema handling
    """

    def test_happy_minimal_request(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Minimal request with just session_id and text."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {"parts": [{"type": "text", "text": "Response"}]}}
            result = send_session_prompt("session-123", "Hello")
            assert result["info"]["parts"][0]["text"] == "Response"
            mock.assert_called_once()
            call_args = mock.call_args
            assert "/session/session-123/message" in call_args[0][0]
            body = call_args[0][1]
            assert body["noReply"] is False
            assert body["parts"][0]["text"] == "Hello"

    def test_happy_with_model(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Model specification is included in request."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            model = {"providerID": "openai", "modelID": "gpt-5"}
            send_session_prompt("session-123", "Hello", model=model)
            call_args = mock.call_args
            body = call_args[0][1]
            assert body["model"] == model

    def test_happy_with_output_schema(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Output schema is included for structured output."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            schema = {"type": "object", "properties": {"key": {"type": "string"}}}
            send_session_prompt("session-123", "Hello", output_schema=schema)
            call_args = mock.call_args
            body = call_args[0][1]
            assert "format" in body
            assert body["format"]["type"] == "json_schema"
            assert body["format"]["schema"] == schema

    def test_happy_uses_server_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Server URL is resolved and used."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            send_session_prompt("session-123", "Hello")
            mock.assert_called_once()
            call_url = mock.call_args[0][0]
            assert "/session/session-123/message" in call_url

    def test_bad_empty_session_id(self):
        """Bad: Empty session_id raises APIError."""
        with pytest.raises(APIError) as exc_info:
            send_session_prompt("", "Hello")
        assert "session_id" in str(exc_info.value).lower()

    def test_bad_none_session_id(self):
        """Bad: None session_id raises APIError."""
        with pytest.raises(APIError) as exc_info:
            send_session_prompt(None, "Hello")  # type: ignore
        assert "session_id" in str(exc_info.value).lower()


class TestSendSessionCommand:
    """Tests for executing commands in sessions."""

    def test_happy_basic_command(self):
        """Happy: Basic command execution."""
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {"parts": [{"type": "text", "text": "OK"}]}}
            result = send_session_command("session-123", "/plan")
            assert result["info"]["parts"][0]["text"] == "OK"
            mock.assert_called_once()
            call_args = mock.call_args
            assert "/session/session-123/command" in call_args[0][0]
            body = call_args[0][1]
            assert body["command"] == "/plan"
            assert body["arguments"] == []

    def test_bad_empty_session_id(self):
        """Bad: Empty session_id raises APIError."""
        with pytest.raises(APIError):
            send_session_command("", "/plan")

    def test_bad_empty_command(self):
        """Bad: Empty command raises APIError."""
        with pytest.raises(APIError):
            send_session_command("session-123", "")


class TestCheckServerHealth:
    """Tests for server health check - uses GET /global/health."""

    def test_happy_healthy_server(self):
        """Happy: Healthy server returns True."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as url_mock:
                url_mock.return_value = "http://localhost:4096"
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.read.return_value = b'{"healthy": true}'
                result = check_server_health()
                assert result is True

    def test_happy_unhealthy_server(self):
        """Happy: Unhealthy server returns False."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as url_mock:
                url_mock.return_value = "http://localhost:4096"
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.read.return_value = b'{"healthy": false}'
                result = check_server_health()
                assert result is False

    def test_bad_server_unavailable(self):
        """Bad: Server not available returns False."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as url_mock:
                url_mock.return_value = "http://localhost:4096"
                mock_urlopen.side_effect = Exception("Connection refused")
                result = check_server_health()
                assert result is False
