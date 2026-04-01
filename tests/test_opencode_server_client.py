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
    _retry_with_backoff,
    check_server_health,
    extract_session_response,
    post_json,
    resolve_opencode_server_base_url,
    send_session_command,
    send_session_prompt,
)


class TestResolveServerBaseUrl:
    """Tests for server URL resolution.

    Priority: opencode.json (SSOT) > OPENCODE_PORT > fail-closed

    Happy: Valid config produces correct URL
    Bad: Missing config raises error
    Corner: Edge cases in env var handling
    """

    def _clear_env(self, monkeypatch: pytest.MonkeyPatch):
        """Clear all server URL related env vars."""
        monkeypatch.delenv("OPENCODE_PORT", raising=False)

    def _mock_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Mock home directory for opencode.json."""
        home = tmp_path / "home"
        home.mkdir(parents=True)
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        return config_dir

    def test_happy_opencode_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: opencode.json with server.hostname and server.port."""
        self._clear_env(monkeypatch)
        config_dir = self._mock_home(monkeypatch, tmp_path)
        config = {"server": {"hostname": "192.168.1.100", "port": 7000}}
        (config_dir / "opencode.json").write_text(json.dumps(config))
        result = resolve_opencode_server_base_url()
        assert result == "http://192.168.1.100:7000"

    def test_happy_opencode_json_default_hostname(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: opencode.json with only port defaults to 127.0.0.1."""
        self._clear_env(monkeypatch)
        config_dir = self._mock_home(monkeypatch, tmp_path)
        config = {"server": {"port": 4096}}
        (config_dir / "opencode.json").write_text(json.dumps(config))
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:4096"

    def test_happy_opencode_port(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: OPENCODE_PORT fallback produces correct localhost URL."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        monkeypatch.setenv("OPENCODE_PORT", "5000")
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:5000"

    def test_happy_opencode_json_priority_over_port(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: opencode.json takes priority over OPENCODE_PORT."""
        self._clear_env(monkeypatch)
        config_dir = self._mock_home(monkeypatch, tmp_path)
        config = {"server": {"hostname": "config-host", "port": 9000}}
        (config_dir / "opencode.json").write_text(json.dumps(config))
        monkeypatch.setenv("OPENCODE_PORT", "5000")
        with pytest.warns(RuntimeWarning, match="drift detected"):
            result = resolve_opencode_server_base_url()
        assert result == "http://config-host:9000"

    def test_bad_no_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Bad: Missing opencode.json and OPENCODE_PORT raises error."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        with pytest.raises(ServerNotAvailableError) as exc_info:
            resolve_opencode_server_base_url()
        assert "not resolvable" in str(exc_info.value).lower()

    def test_corner_whitespace_only(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Corner: Whitespace-only OPENCODE_PORT is treated as empty."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        monkeypatch.setenv("OPENCODE_PORT", "   ")
        with pytest.raises(ServerNotAvailableError):
            resolve_opencode_server_base_url()

    def test_bad_invalid_opencode_port_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Bad: invalid OPENCODE_PORT fails closed when no opencode.json is usable."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        monkeypatch.setenv("OPENCODE_PORT", "70000")
        with pytest.raises(ServerNotAvailableError, match="OPENCODE_PORT"):
            resolve_opencode_server_base_url()

    def test_corner_invalid_env_ignored_when_json_authoritative(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ):
        """Corner: invalid OPENCODE_PORT is warned and ignored if opencode.json is valid."""
        self._clear_env(monkeypatch)
        config_dir = self._mock_home(monkeypatch, tmp_path)
        (config_dir / "opencode.json").write_text(
            json.dumps({"server": {"hostname": "127.0.0.1", "port": 4096}})
        )
        monkeypatch.setenv("OPENCODE_PORT", "invalid")
        with pytest.warns(RuntimeWarning, match="invalid and ignored"):
            result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:4096"

    def test_corner_config_missing_opencode_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Corner: opencode.json missing server config."""
        self._clear_env(monkeypatch)
        config_dir = self._mock_home(monkeypatch, tmp_path)
        config = {"review": {"phase5_max_review_iterations": 3}}
        (config_dir / "opencode.json").write_text(json.dumps(config))
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
        """Happy: Minimal request with session_id from env and text."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "session-123")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {"parts": [{"type": "text", "text": "Response"}]}}
            result = send_session_prompt(text="Hello")
            assert result["info"]["parts"][0]["text"] == "Response"
            mock.assert_called_once()
            call_args = mock.call_args
            assert "/session/session-123/message" in call_args[0][0]
            body = call_args[0][1]
            assert body["noReply"] is False
            assert body["parts"][0]["text"] == "Hello"

    def test_happy_with_model(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Model specification is included in request."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "session-123")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            model = {"providerID": "openai", "modelID": "gpt-5"}
            send_session_prompt(text="Hello", model=model)
            call_args = mock.call_args
            body = call_args[0][1]
            assert body["model"] == model

    def test_happy_with_output_schema(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Output schema is included for structured output."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "session-123")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            schema = {"type": "object", "properties": {"key": {"type": "string"}}}
            send_session_prompt(text="Hello", output_schema=schema)
            call_args = mock.call_args
            body = call_args[0][1]
            assert "format" in body
            assert body["format"]["type"] == "json_schema"
            assert body["format"]["schema"] == schema

    def test_happy_uses_server_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Server URL is resolved and used."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "session-123")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            send_session_prompt(text="Hello")
            mock.assert_called_once()
            call_url = mock.call_args[0][0]
            assert "/session/session-123/message" in call_url

    def test_bad_missing_session_id(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Missing OPENCODE_SESSION_ID raises APIError."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with pytest.raises(APIError) as exc_info:
            send_session_prompt(text="Hello")
        assert "OPENCODE_SESSION_ID" in str(exc_info.value)

    def test_bad_empty_session_id(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Empty OPENCODE_SESSION_ID raises APIError."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "")
        with pytest.raises(APIError) as exc_info:
            send_session_prompt(text="Hello")
        assert "OPENCODE_SESSION_ID" in str(exc_info.value)


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
        """Happy: Healthy server returns dict with healthy=True."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as url_mock:
                url_mock.return_value = "http://localhost:4096"
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.read.return_value = b'{"healthy": true, "version": "1.3.7"}'
                result = check_server_health()
                assert result.get("healthy") is True

    def test_happy_unhealthy_server(self):
        """Happy: Unhealthy server returns dict with healthy=False."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as url_mock:
                url_mock.return_value = "http://localhost:4096"
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.read.return_value = b'{"healthy": false}'
                result = check_server_health()
                assert result.get("healthy") is False

    def test_bad_server_unavailable(self):
        """Bad: Server not available raises ServerNotAvailableError."""
        from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as url_mock:
                url_mock.return_value = "http://localhost:4096"
                mock_urlopen.side_effect = Exception("Connection refused")
                with pytest.raises(ServerNotAvailableError):
                    check_server_health()


class TestRetryWithBackoff:
    """Tests for retry wrapper with backoff.

    Happy: Retry succeeds on second attempt
    Bad: All retries fail -> fail-closed
    Edge: Non-retryable exceptions bypass retry
    """

    def test_happy_retry_succeeds_on_second_attempt(self):
        """Happy: First attempt fails, second succeeds."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ServerNotAvailableError("Connection failed")
            return "success"

        result = _retry_with_backoff(flaky_func, max_attempts=3, backoff_ms=10)
        assert result == "success"
        assert call_count == 2

    def test_happy_retry_succeeds_on_third_attempt(self):
        """Happy: Third attempt succeeds."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ServerNotAvailableError(f"Attempt {call_count} failed")
            return "success"

        result = _retry_with_backoff(flaky_func, max_attempts=3, backoff_ms=10)
        assert result == "success"
        assert call_count == 3

    def test_bad_all_retries_fail_fails_closed(self):
        """Bad: All attempts fail -> raises last exception."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            raise ServerNotAvailableError(f"Attempt {call_count} failed")

        with pytest.raises(ServerNotAvailableError) as exc_info:
            _retry_with_backoff(flaky_func, max_attempts=3, backoff_ms=10)
        assert "Attempt 3 failed" in str(exc_info.value)
        assert call_count == 3

    def test_edge_non_retryable_exception_bypasses_retry(self):
        """Edge: Non-retryable exceptions (APIError) are not retried."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            raise APIError("Invalid request")

        with pytest.raises(APIError):
            _retry_with_backoff(
                flaky_func,
                max_attempts=3,
                backoff_ms=10,
                retryable_exceptions=(ServerNotAvailableError, TimeoutError),
            )
        assert call_count == 1

    def test_happy_single_attempt_succeeds_no_retry(self):
        """Happy: First attempt succeeds -> no retry."""
        call_count = 0

        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = _retry_with_backoff(success_func, max_attempts=3)
        assert result == "success"
        assert call_count == 1


class TestPostJsonRetry:
    """Tests for post_json with retry parameter."""

    def test_happy_retry_enabled(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: post_json with retry=True uses retry wrapper."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._retry_with_backoff") as mock_retry:
            mock_retry.return_value = {"success": True}
            result = post_json("/test", {"key": "value"}, retry=True, max_attempts=3, backoff_ms=10)
            assert result == {"success": True}
            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args[1]
            assert call_kwargs["max_attempts"] == 3
            assert call_kwargs["backoff_ms"] == 10

    def test_bad_retry_disabled_bypasses_wrapper(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: post_json with retry=False makes direct request."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._retry_with_backoff") as mock_retry:
            mock_retry.return_value = {"success": True}
            with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.read.return_value = b'{"success": true}'
                result = post_json("/test", {"key": "value"}, retry=False)
                assert result == {"success": True}
                mock_retry.assert_not_called()

    def test_happy_default_no_retry(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Default behavior (retry not specified) makes direct request."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._retry_with_backoff") as mock_retry:
            mock_retry.return_value = {"success": True}
            with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.read.return_value = b'{"success": true}'
                result = post_json("/test", {"key": "value"})
                assert result == {"success": True}
                mock_retry.assert_not_called()
