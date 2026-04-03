from __future__ import annotations

import json
import os
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from governance_runtime.infrastructure.opencode_server_client import (
    APIError,
    AuthenticationError,
    ProjectNotFoundError,
    ProjectSessionNotFoundError,
    ServerAuthRequiredError,
    ServerDiscoveryAmbiguousError,
    ServerDiscoveryNotFoundError,
    ServerDiscoveryUnsupportedPlatformError,
    ServerMode,
    ServerNotAvailableError,
    ServerStartFailedError,
    ServerStartTimeoutError,
    ServerTargetUnhealthyError,
    _check_target_server_health,
    _parse_lsof_candidates,
    _retry_with_backoff,
    check_server_health,
    discover_local_opencode_server,
    ensure_opencode_server_running,
    extract_session_response,
    get_active_session,
    get_projects,
    post_json,
    resolve_opencode_server_base_url,
    resolve_project_id,
    resolve_server_mode,
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

    def test_happy_session_state_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: SESSION_STATE.SessionHydration.resolved_server_url resolves URL."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        # No opencode.json, no OPENCODE_PORT — only SESSION_STATE has the URL
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: "http://127.0.0.1:52372",
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:52372"

    def test_session_state_overrides_opencode_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: SESSION_STATE hydrated URL takes priority over opencode.json.

        Rationale: OpenCode Desktop starts on random ports.  The hydrated URL
        reflects the *actual* running server discovered by lsof, whereas
        opencode.json contains a stale installer default (e.g. 4096).
        """
        self._clear_env(monkeypatch)
        config_dir = self._mock_home(monkeypatch, tmp_path)
        config = {"server": {"port": 4096}}
        (config_dir / "opencode.json").write_text(json.dumps(config))
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: "http://127.0.0.1:52372",
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:52372", "SESSION_STATE must override opencode.json"

    def test_session_state_overrides_opencode_port(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Happy: SESSION_STATE URL takes priority over OPENCODE_PORT."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        monkeypatch.setenv("OPENCODE_PORT", "9999")
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: "http://127.0.0.1:52372",
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:52372", "SESSION_STATE must override OPENCODE_PORT"

    def test_session_state_none_falls_through(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Edge: SESSION_STATE returns None, resolution falls through to OPENCODE_PORT."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        monkeypatch.setenv("OPENCODE_PORT", "8080")
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: None,
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:8080"

    def test_session_state_empty_string_falls_through(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Edge: SESSION_STATE returns empty string, resolution falls through."""
        self._clear_env(monkeypatch)
        self._mock_home(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: "",
        )
        with pytest.raises(ServerNotAvailableError):
            resolve_opencode_server_base_url()


class TestReadServerUrlFromState:
    """Tests for _read_server_url_from_state() helper.

    This function reads SessionHydration.resolved_server_url from SESSION_STATE.
    It must be fail-safe: any error → None.
    """

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def _mock_state(self, session_hydration: dict | None, state: dict | None = None):
        """Create a mock that simulates reading SESSION_STATE."""
        from governance_runtime.infrastructure.opencode_server_client import _read_server_url_from_state

        if state is None:
            state = {}
        if session_hydration is not None:
            state["SessionHydration"] = session_hydration

        def mock_resolve():
            return (Path("/fake/SESSION_STATE.json"), "fp", Path("/fake/ws"), Path("/fake/wd"))

        def mock_load(path):
            return {"SESSION_STATE": state}

        return _read_server_url_from_state, mock_resolve, mock_load

    def test_happy_returns_url(self, monkeypatch):
        """Happy: returns resolved_server_url when status is hydrated."""
        fn, mock_resolve, mock_load = self._mock_state({
            "status": "hydrated",
            "hydrated_session_id": "ses_abc",
            "resolved_server_url": "http://127.0.0.1:52372",
        })
        monkeypatch.setattr(
            f"{self._MODULE}.resolve_active_session_paths" if False else
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            mock_resolve,
        )
        monkeypatch.setattr(
            "governance_runtime.infrastructure.json_store.load_json",
            mock_load,
        )
        result = fn()
        assert result == "http://127.0.0.1:52372"

    def test_returns_none_when_not_hydrated(self, monkeypatch):
        """Bad: returns None when status is not_hydrated."""
        fn, mock_resolve, mock_load = self._mock_state({
            "status": "not_hydrated",
            "resolved_server_url": "http://127.0.0.1:52372",
        })
        monkeypatch.setattr(
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            mock_resolve,
        )
        monkeypatch.setattr(
            "governance_runtime.infrastructure.json_store.load_json",
            mock_load,
        )
        result = fn()
        assert result is None

    def test_returns_none_when_url_missing(self, monkeypatch):
        """Edge: returns None when hydrated but resolved_server_url is absent."""
        fn, mock_resolve, mock_load = self._mock_state({
            "status": "hydrated",
            "hydrated_session_id": "ses_abc",
        })
        monkeypatch.setattr(
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            mock_resolve,
        )
        monkeypatch.setattr(
            "governance_runtime.infrastructure.json_store.load_json",
            mock_load,
        )
        result = fn()
        assert result is None

    def test_returns_none_when_url_empty(self, monkeypatch):
        """Edge: returns None when resolved_server_url is empty string."""
        fn, mock_resolve, mock_load = self._mock_state({
            "status": "hydrated",
            "resolved_server_url": "   ",
        })
        monkeypatch.setattr(
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            mock_resolve,
        )
        monkeypatch.setattr(
            "governance_runtime.infrastructure.json_store.load_json",
            mock_load,
        )
        result = fn()
        assert result is None

    def test_returns_none_when_no_session_state(self, monkeypatch):
        """Corner: returns None when SESSION_STATE key is missing."""
        from governance_runtime.infrastructure.opencode_server_client import _read_server_url_from_state

        monkeypatch.setattr(
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            lambda: (Path("/fake/s.json"), "fp", Path("/fake/ws"), Path("/fake/wd")),
        )
        monkeypatch.setattr(
            "governance_runtime.infrastructure.json_store.load_json",
            lambda p: {},
        )
        assert _read_server_url_from_state() is None

    def test_returns_none_on_exception(self, monkeypatch):
        """Corner: any exception returns None (fail-safe)."""
        from governance_runtime.infrastructure.opencode_server_client import _read_server_url_from_state

        monkeypatch.setattr(
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            lambda: (_ for _ in ()).throw(RuntimeError("session locator broken")),
        )
        assert _read_server_url_from_state() is None

    def test_returns_none_when_hydration_not_dict(self, monkeypatch):
        """Corner: returns None when SessionHydration is a string, not dict."""
        from governance_runtime.infrastructure.opencode_server_client import _read_server_url_from_state

        monkeypatch.setattr(
            "governance_runtime.infrastructure.session_locator.resolve_active_session_paths",
            lambda: (Path("/fake/s.json"), "fp", Path("/fake/ws"), Path("/fake/wd")),
        )
        monkeypatch.setattr(
            "governance_runtime.infrastructure.json_store.load_json",
            lambda p: {"SESSION_STATE": {"SessionHydration": "hydrated"}},
        )
        assert _read_server_url_from_state() is None


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


class TestEnsureOpencodeServerRunning:
    """Tests for ensure_opencode_server_running lifecycle manager.

    Happy: target server healthy -> reuse
    Happy: target server absent -> auto-start -> healthy
    Bad: target server unhealthy -> blocked
    Bad: start fails -> blocked
    Bad: start timeout -> blocked
    Edge: port not resolvable -> blocked
    """

    def test_happy_target_healthy_reuse(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: healthy server on target -> reuse immediately."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            mock_health.return_value = {"healthy": True, "version": "1.2.3"}
            result = ensure_opencode_server_running(hostname="127.0.0.1", port=4096)

            assert result["healthy"] is True
            assert result["started"] is False
            assert result["version"] == "1.2.3"
            mock_health.assert_called_once()

    def test_happy_target_absent_auto_start_becomes_healthy(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: server absent -> auto-start -> becomes healthy."""
        call_count = 0

        def health_check_sequence(hostname, port, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ServerNotAvailableError("not running")
            if call_count == 2:
                raise ServerNotAvailableError("starting up")
            return {"healthy": True, "version": "1.2.3"}

        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            with patch("governance_runtime.infrastructure.opencode_server_client.subprocess.Popen") as mock_popen:
                mock_proc = mock_popen.return_value
                mock_proc.wait.return_value = None
                mock_proc.terminate.return_value = None
                mock_health.side_effect = health_check_sequence

                with patch("governance_runtime.infrastructure.opencode_server_client.time.sleep"):
                    result = ensure_opencode_server_running(
                        hostname="127.0.0.1",
                        port=4096,
                        startup_timeout_seconds=5,
                    )

                    assert result["healthy"] is True
                    assert result["started"] is True
                    mock_popen.assert_called_once()

    def test_bad_target_unhealthy_returns_blocked(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: server reachable but unhealthy -> blocked immediately."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            mock_health.return_value = {"healthy": False, "version": "1.2.3"}

            with pytest.raises(ServerTargetUnhealthyError) as exc_info:
                ensure_opencode_server_running(hostname="127.0.0.1", port=4096)

            error_msg = str(exc_info.value).lower()
            assert "reachable but unhealthy" in error_msg or "not healthy" in error_msg

    def test_bad_start_fails_command_not_found(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: opencode command not found -> blocked."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            mock_health.side_effect = ServerNotAvailableError("not running")

            with patch("governance_runtime.infrastructure.opencode_server_client.subprocess.Popen") as mock_popen:
                mock_popen.side_effect = FileNotFoundError("opencode not found")

                with pytest.raises(ServerStartFailedError) as exc_info:
                    ensure_opencode_server_running(hostname="127.0.0.1", port=4096)

                assert "not found" in str(exc_info.value).lower()

    def test_bad_start_timeout(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: server doesn't become healthy within timeout -> blocked."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            mock_health.side_effect = ServerNotAvailableError("not running")

            with patch("governance_runtime.infrastructure.opencode_server_client.subprocess.Popen") as mock_popen:
                mock_proc = mock_popen.return_value
                mock_proc.wait.return_value = None
                mock_proc.terminate.return_value = None
                mock_proc.wait.side_effect = None

                mock_health.side_effect = ServerNotAvailableError("still not running")

                with patch("governance_runtime.infrastructure.opencode_server_client.time.sleep"):
                    with pytest.raises(ServerStartTimeoutError) as exc_info:
                        ensure_opencode_server_running(
                            hostname="127.0.0.1",
                            port=4096,
                            startup_timeout_seconds=1,
                        )

                assert "timeout" in str(exc_info.value).lower()

    def test_edge_port_not_resolvable(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: port not resolvable -> uses defaults when server available."""
        monkeypatch.setenv("OPENCODE_PORT", "")

        with patch("governance_runtime.infrastructure.opencode_server_client._resolve_server_endpoint_from_opencode_json") as mock_resolve:
            with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
                mock_resolve.return_value = (None, None)
                mock_health.return_value = {"healthy": True, "version": "1.0.0"}

                result = ensure_opencode_server_running()

                assert result["healthy"] is True
                assert result["started"] is False

    def test_happy_uses_config_when_no_explicit_params(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: uses opencode.json config when no explicit hostname/port."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        with patch("governance_runtime.infrastructure.opencode_server_client._resolve_server_endpoint_from_opencode_json") as mock_resolve:
            mock_resolve.return_value = ("192.168.1.100", 8192)

            with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
                mock_health.return_value = {"healthy": True, "version": "1.2.3"}

                result = ensure_opencode_server_running()

                assert result["healthy"] is True
                mock_health.assert_called_once_with(hostname="192.168.1.100", port=8192, timeout=10)


class TestPopenPlatformDetachment:
    """Tests for platform-aware process detachment in ensure_opencode_server_running.

    On Windows, the managed server must use CREATE_NEW_PROCESS_GROUP |
    DETACHED_PROCESS instead of start_new_session=True, which is silently
    ignored on Windows.
    """

    def test_unix_uses_start_new_session(self, monkeypatch: pytest.MonkeyPatch):
        """Unix: Popen receives start_new_session=True, no creationflags."""
        monkeypatch.setattr("governance_runtime.infrastructure.opencode_server_client.sys.platform", "darwin")
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        call_count = 0

        def health_side_effect(hostname, port, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ServerNotAvailableError("not running")
            return {"healthy": True, "version": "1.0.0"}

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            with patch("governance_runtime.infrastructure.opencode_server_client.subprocess.Popen") as mock_popen:
                with patch("governance_runtime.infrastructure.opencode_server_client.time.sleep"):
                    mock_health.side_effect = health_side_effect
                    mock_popen.return_value.wait.return_value = None

                    ensure_opencode_server_running(hostname="127.0.0.1", port=4096)

                    mock_popen.assert_called_once()
                    call_kwargs = mock_popen.call_args
                    assert call_kwargs.kwargs.get("start_new_session") is True or call_kwargs[1].get("start_new_session") is True
                    assert "creationflags" not in (call_kwargs.kwargs or call_kwargs[1])

    def test_windows_uses_creationflags(self, monkeypatch: pytest.MonkeyPatch):
        """Windows: Popen receives CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS, no start_new_session."""
        monkeypatch.setattr("governance_runtime.infrastructure.opencode_server_client.sys.platform", "win32")
        monkeypatch.setenv("OPENCODE_PORT", "4096")

        call_count = 0

        def health_side_effect(hostname, port, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ServerNotAvailableError("not running")
            return {"healthy": True, "version": "1.0.0"}

        # These constants only exist on Windows; use their known values for
        # cross-platform test execution.
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        expected_flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS

        with patch("governance_runtime.infrastructure.opencode_server_client._check_target_server_health") as mock_health:
            with patch("governance_runtime.infrastructure.opencode_server_client.subprocess.Popen") as mock_popen:
                with patch("governance_runtime.infrastructure.opencode_server_client.time.sleep"):
                    mock_health.side_effect = health_side_effect
                    mock_popen.return_value.wait.return_value = None

                    ensure_opencode_server_running(hostname="127.0.0.1", port=4096)

                    mock_popen.assert_called_once()
                    call_kwargs = mock_popen.call_args
                    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
                    assert kwargs.get("creationflags") == expected_flags
                    assert "start_new_session" not in kwargs


class TestCheckTargetServerHealth:
    """Tests for _check_target_server_health internal function."""

    def test_happy_healthy_response(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: valid healthy response."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.read.return_value = b'{"healthy": true, "version": "1.0.0"}'

            result = _check_target_server_health("127.0.0.1", 4096, timeout=5)

            assert result == {"healthy": True, "version": "1.0.0"}

    def test_bad_http_error(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: server returns HTTP error."""
        import urllib.error

        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "http://127.0.0.1:4096/global/health",
                500,
                "Internal Server Error",
                {},
                None,
            )

            with pytest.raises(ServerNotAvailableError) as exc_info:
                _check_target_server_health("127.0.0.1", 4096)

            assert "500" in str(exc_info.value)

    def test_bad_connection_refused(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: connection refused."""
        import urllib.error

        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            with pytest.raises(ServerNotAvailableError) as exc_info:
                _check_target_server_health("127.0.0.1", 4096)

            assert "Connection refused" in str(exc_info.value)

    def test_bad_invalid_json(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: invalid JSON response."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.read.return_value = b"not valid json"

            with pytest.raises(ServerNotAvailableError) as exc_info:
                _check_target_server_health("127.0.0.1", 4096)

            assert "JSON" in str(exc_info.value) or "Expecting value" in str(exc_info.value)

    def test_bad_non_dict_response(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: response is not a dict."""
        with patch("governance_runtime.infrastructure.opencode_server_client.urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.read.return_value = b'"just a string"'

            with pytest.raises(ServerNotAvailableError) as exc_info:
                _check_target_server_health("127.0.0.1", 4096)

            assert "expected dict" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ServerMode + resolve_server_mode() tests
# ---------------------------------------------------------------------------


class TestServerMode:
    """Tests for ServerMode enum and resolve_server_mode().

    Happy: Valid mode strings resolve correctly
    Bad: Invalid mode strings raise ValueError
    Corner: Whitespace handling, case insensitivity
    Edge: Resolution order (CLI > ENV > default)
    """

    def test_happy_enum_values(self):
        """Happy: Enum has exactly two members with correct values."""
        assert ServerMode.ATTACH_EXISTING.value == "attach_existing"
        assert ServerMode.MANAGED.value == "managed"
        assert len(ServerMode) == 2

    def test_happy_default_is_attach_existing(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Default mode is attach_existing when no CLI or ENV."""
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)
        assert resolve_server_mode() is ServerMode.ATTACH_EXISTING

    def test_happy_cli_attach_existing(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: CLI value 'attach_existing' resolves correctly."""
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)
        assert resolve_server_mode("attach_existing") is ServerMode.ATTACH_EXISTING

    def test_happy_cli_managed(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: CLI value 'managed' resolves correctly."""
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)
        assert resolve_server_mode("managed") is ServerMode.MANAGED

    def test_happy_env_attach_existing(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: ENV 'attach_existing' resolves when no CLI."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "attach_existing")
        assert resolve_server_mode() is ServerMode.ATTACH_EXISTING

    def test_happy_env_managed(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: ENV 'managed' resolves when no CLI."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "managed")
        assert resolve_server_mode() is ServerMode.MANAGED

    def test_edge_cli_overrides_env(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: CLI value takes priority over ENV."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "managed")
        assert resolve_server_mode("attach_existing") is ServerMode.ATTACH_EXISTING

    def test_edge_cli_managed_overrides_env_attach(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: CLI 'managed' overrides ENV 'attach_existing'."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "attach_existing")
        assert resolve_server_mode("managed") is ServerMode.MANAGED

    def test_corner_case_insensitive_cli(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: CLI values are case-insensitive."""
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)
        assert resolve_server_mode("MANAGED") is ServerMode.MANAGED
        assert resolve_server_mode("Attach_Existing") is ServerMode.ATTACH_EXISTING

    def test_corner_case_insensitive_env(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: ENV values are case-insensitive."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "MANAGED")
        assert resolve_server_mode() is ServerMode.MANAGED

    def test_corner_whitespace_cli(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: CLI whitespace is stripped."""
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)
        assert resolve_server_mode("  managed  ") is ServerMode.MANAGED

    def test_corner_whitespace_env(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: ENV whitespace is stripped."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "  attach_existing  ")
        assert resolve_server_mode() is ServerMode.ATTACH_EXISTING

    def test_corner_empty_env_uses_default(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: Empty ENV falls through to default."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "")
        assert resolve_server_mode() is ServerMode.ATTACH_EXISTING

    def test_corner_whitespace_only_env_uses_default(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: Whitespace-only ENV falls through to default."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "   ")
        assert resolve_server_mode() is ServerMode.ATTACH_EXISTING

    def test_bad_invalid_cli_value(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Invalid CLI value raises ValueError."""
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)
        with pytest.raises(ValueError, match="Invalid server mode"):
            resolve_server_mode("auto_discover")

    def test_bad_invalid_env_value(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Invalid ENV value raises ValueError."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "hybrid")
        with pytest.raises(ValueError, match="Invalid server mode"):
            resolve_server_mode()

    def test_bad_invalid_cli_overrides_valid_env(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Invalid CLI value raises even when ENV is valid."""
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "managed")
        with pytest.raises(ValueError, match="Invalid server mode"):
            resolve_server_mode("bogus")


# ---------------------------------------------------------------------------
# _parse_lsof_candidates() tests
# ---------------------------------------------------------------------------


class TestParseLsofCandidates:
    """Tests for _parse_lsof_candidates().

    Happy: Standard lsof output is parsed correctly
    Bad: Malformed lines are skipped
    Corner: IPv6, duplicate ports, non-opencode processes
    Edge: Real-world lsof output from macOS
    """

    REAL_LSOF_LINE = (
        "opencode- 53525 koeppben   11u  IPv4 0xabc123  0t0  TCP 127.0.0.1:52372 (LISTEN)"
    )

    def test_happy_single_opencode_listener(self):
        """Happy: Single opencode listener is extracted."""
        candidates = _parse_lsof_candidates(self.REAL_LSOF_LINE)
        assert candidates == [("127.0.0.1", 52372)]

    def test_happy_multiple_opencode_listeners(self):
        """Happy: Multiple listeners on different ports."""
        output = (
            "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "opencode  53530 user   12u  IPv4 0x2  0t0  TCP 127.0.0.1:52373 (LISTEN)\n"
        )
        candidates = _parse_lsof_candidates(output)
        assert candidates == [("127.0.0.1", 52372), ("127.0.0.1", 52373)]

    def test_happy_filters_non_opencode_processes(self):
        """Happy: Non-opencode processes are filtered out."""
        output = (
            "node      1234 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:3000 (LISTEN)\n"
            "opencode- 5678 user   12u  IPv4 0x2  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "postgres  9012 user   13u  IPv4 0x3  0t0  TCP 127.0.0.1:5432 (LISTEN)\n"
        )
        candidates = _parse_lsof_candidates(output)
        assert candidates == [("127.0.0.1", 52372)]

    def test_corner_deduplicates_same_port(self):
        """Corner: Same host:port from multiple file descriptors is deduplicated."""
        output = (
            "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "opencode- 53525 user   12u  IPv4 0x2  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
        )
        candidates = _parse_lsof_candidates(output)
        assert candidates == [("127.0.0.1", 52372)]

    def test_corner_empty_output(self):
        """Corner: Empty lsof output returns no candidates."""
        assert _parse_lsof_candidates("") == []

    def test_corner_header_line_skipped(self):
        """Corner: lsof header line is skipped (fewer than 9 columns)."""
        output = "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
        assert _parse_lsof_candidates(output) == []

    def test_bad_malformed_port(self):
        """Bad: Non-numeric port is skipped."""
        output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:abc (LISTEN)\n"
        assert _parse_lsof_candidates(output) == []

    def test_bad_out_of_range_port(self):
        """Bad: Port outside valid range is skipped."""
        output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:70000 (LISTEN)\n"
        assert _parse_lsof_candidates(output) == []

    def test_bad_no_listen_marker(self):
        """Bad: Line without (LISTEN) marker is skipped."""
        output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (ESTABLISHED)\n"
        assert _parse_lsof_candidates(output) == []

    def test_edge_real_macos_output_with_mixed_processes(self):
        """Edge: Real-world macOS lsof output with mixed processes."""
        output = (
            "COMMAND     PID     USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\n"
            "launchd       1     root    7u  IPv6 0xabc123      0t0  TCP *:22 (LISTEN)\n"
            "opencode- 53525 koeppben   11u  IPv4 0xdef456      0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "Google    54000 koeppben   23u  IPv4 0xghi789      0t0  TCP 127.0.0.1:9222 (LISTEN)\n"
        )
        candidates = _parse_lsof_candidates(output)
        assert candidates == [("127.0.0.1", 52372)]

    def test_corner_opencode_without_dash(self):
        """Corner: Process named 'opencode' (no dash) is also matched."""
        output = "opencode  53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:4096 (LISTEN)\n"
        candidates = _parse_lsof_candidates(output)
        assert candidates == [("127.0.0.1", 4096)]

    def test_corner_ipv6_bracket_notation(self):
        """Corner: IPv6 bracket notation is parsed correctly."""
        output = "opencode- 53525 user   11u  IPv6 0x1  0t0  TCP [::1]:52372 (LISTEN)\n"
        candidates = _parse_lsof_candidates(output)
        assert candidates == [("[::1]", 52372)]


# ---------------------------------------------------------------------------
# discover_local_opencode_server() tests
# ---------------------------------------------------------------------------


class TestDiscoverLocalOpencodeServer:
    """Tests for discover_local_opencode_server().

    Happy: Single healthy server is discovered
    Bad: No listeners, lsof failures
    Corner: Multiple listeners but only one healthy
    Edge: Auth required, platform check
    """

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def _mock_lsof(self, stdout: str, returncode: int = 0):
        """Create a mock subprocess.CompletedProcess for lsof."""
        return subprocess.CompletedProcess(
            args=["lsof", "-iTCP@127.0.0.1", "-sTCP:LISTEN", "-nP"],
            returncode=returncode,
            stdout=stdout,
            stderr="",
        )

    def _mock_urlopen_for_candidates(
        self,
        healthy_ports: set[int],
        auth_required_ports: set[int] | None = None,
    ):
        """Create a side_effect function for urlopen that responds per port.

        Ports in ``healthy_ports`` return ``{"healthy": true}``.
        Ports in ``auth_required_ports`` return HTTP 401.
        All others raise URLError (connection refused).
        """
        auth_required_ports = auth_required_ports or set()

        def side_effect(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            # Extract port from URL like http://127.0.0.1:52372/global/health
            port_str = url.split(":")[-1].split("/")[0]
            port = int(port_str)

            if port in auth_required_ports:
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

            if port in healthy_ports:
                resp = MagicMock()
                resp.__enter__ = MagicMock(return_value=resp)
                resp.__exit__ = MagicMock(return_value=False)
                resp.read.return_value = json.dumps({"healthy": True, "version": "1.3.7"}).encode()
                return resp

            raise urllib.error.URLError("Connection refused")

        return side_effect

    def test_happy_single_healthy_server(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Single opencode listener that is healthy → returns base_url + health."""
        lsof_output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates({52372})):
                base_url, health = discover_local_opencode_server()

        assert base_url == "http://127.0.0.1:52372"
        assert health["healthy"] is True


class TestBaseUrlThreading:
    """Tests for base_url parameter threading in server client functions.

    Verifies that when base_url is provided, resolve_opencode_server_base_url()
    is NOT called — the provided URL is used directly.

    Happy: Provided base_url is used for HTTP requests
    Corner: base_url=None falls back to resolve_opencode_server_base_url()
    """

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def test_happy_get_sessions_uses_provided_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: get_sessions(base_url=...) uses the provided URL, not resolve."""
        from governance_runtime.infrastructure.opencode_server_client import get_sessions

        captured = {}

        def mock_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'[{"id": "ses_1"}]'
            return mock_resp

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
            result = get_sessions(base_url="http://127.0.0.1:52372")

        assert captured["url"] == "http://127.0.0.1:52372/session"
        assert result == [{"id": "ses_1"}]

    def test_happy_get_sessions_base_url_skips_resolve(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: get_sessions(base_url=...) does NOT call resolve_opencode_server_base_url."""
        from governance_runtime.infrastructure.opencode_server_client import get_sessions

        def mock_urlopen(req, **kwargs):
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'[]'
            return mock_resp

        resolve_called = {"count": 0}
        original_resolve = None

        def mock_resolve():
            resolve_called["count"] += 1
            raise AssertionError("resolve_opencode_server_base_url should not be called when base_url is provided")

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.resolve_opencode_server_base_url", side_effect=mock_resolve):
            with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
                get_sessions(base_url="http://127.0.0.1:52372")

        assert resolve_called["count"] == 0

    def test_happy_get_active_session_threads_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: get_active_session(base_url=...) passes URL to get_sessions."""
        from governance_runtime.infrastructure.opencode_server_client import get_active_session

        captured = {}

        def mock_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'[{"id": "ses_1", "title": "Test"}]'
            return mock_resp

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
            result = get_active_session(base_url="http://127.0.0.1:52372")

        assert captured["url"] == "http://127.0.0.1:52372/session"
        assert result["id"] == "ses_1"

    def test_happy_send_session_message_uses_provided_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: send_session_message(base_url=...) uses the provided URL."""
        from governance_runtime.infrastructure.opencode_server_client import send_session_message

        captured = {}

        def mock_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{}'
            return mock_resp

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
            send_session_message("hello", "ses_123", base_url="http://127.0.0.1:52372")

        assert captured["url"] == "http://127.0.0.1:52372/session/ses_123/message"

    def test_happy_send_session_message_base_url_skips_resolve(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: send_session_message(base_url=...) does NOT call resolve."""
        from governance_runtime.infrastructure.opencode_server_client import send_session_message

        def mock_urlopen(req, **kwargs):
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{}'
            return mock_resp

        resolve_called = {"count": 0}

        def mock_resolve():
            resolve_called["count"] += 1
            raise AssertionError("resolve should not be called")

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.resolve_opencode_server_base_url", side_effect=mock_resolve):
            with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
                send_session_message("hello", "ses_123", base_url="http://127.0.0.1:52372")

        assert resolve_called["count"] == 0

    def test_corner_none_base_url_falls_back_to_resolve(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: base_url=None falls back to resolve_opencode_server_base_url."""
        from governance_runtime.infrastructure.opencode_server_client import get_sessions

        captured = {}

        def mock_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'[]'
            return mock_resp

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.resolve_opencode_server_base_url", return_value="http://127.0.0.1:9999"):
            with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
                get_sessions()  # No base_url → resolve fallback

        assert captured["url"] == "http://127.0.0.1:9999/session"


class TestDiscoverLocalOpencodeServerFailures:
    """Failure and edge-case tests for discover_local_opencode_server().

    These tests cover bad paths, error handling, and edge cases that
    exercise lsof failures, unhealthy candidates, ambiguous matches,
    auth requirements, and platform checks.
    """

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def _mock_lsof(self, stdout: str, returncode: int = 0):
        """Create a mock subprocess.CompletedProcess for lsof."""
        return subprocess.CompletedProcess(
            args=["lsof", "-iTCP@127.0.0.1", "-sTCP:LISTEN", "-nP"],
            returncode=returncode,
            stdout=stdout,
            stderr="",
        )

    def _mock_urlopen_for_candidates(
        self,
        healthy_ports: set[int],
        auth_required_ports: set[int] | None = None,
    ):
        """Create a side_effect function for urlopen that responds per port."""
        auth_required_ports = auth_required_ports or set()

        def side_effect(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            port_str = url.split(":")[-1].split("/")[0]
            port = int(port_str)

            if port in auth_required_ports:
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

            if port in healthy_ports:
                resp = MagicMock()
                resp.__enter__ = MagicMock(return_value=resp)
                resp.__exit__ = MagicMock(return_value=False)
                resp.read.return_value = json.dumps({"healthy": True, "version": "1.3.7"}).encode()
                return resp

            raise urllib.error.URLError("Connection refused")

        return side_effect

    def test_bad_no_opencode_listeners(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: lsof returns output but no opencode-named processes → not found."""
        lsof_output = "node 1234 user 11u IPv4 0x1 0t0 TCP 127.0.0.1:3000 (LISTEN)\n"

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with pytest.raises(ServerDiscoveryNotFoundError, match="No OpenCode server found"):
                discover_local_opencode_server()

    def test_bad_empty_lsof_output(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: lsof returns empty output (no listeners at all)."""
        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof("", returncode=1)):
            with pytest.raises(ServerDiscoveryNotFoundError, match="No OpenCode server found"):
                discover_local_opencode_server()

    def test_bad_lsof_not_found(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: lsof command not found → not found error (not platform error)."""
        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", side_effect=FileNotFoundError("lsof")):
            with pytest.raises(ServerDiscoveryNotFoundError, match="lsof.*not found"):
                discover_local_opencode_server()

    def test_bad_lsof_timeout(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: lsof times out → not found error."""
        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="lsof", timeout=5)):
            with pytest.raises(ServerDiscoveryNotFoundError, match="timed out"):
                discover_local_opencode_server()

    def test_bad_lsof_oserror(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: lsof raises OSError → not found error."""
        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", side_effect=OSError("Permission denied")):
            with pytest.raises(ServerDiscoveryNotFoundError, match="lsof failed"):
                discover_local_opencode_server()

    def test_bad_all_candidates_unhealthy(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Opencode listeners found but none return healthy → not found (with count)."""
        lsof_output = (
            "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "opencode- 53530 user   12u  IPv4 0x2  0t0  TCP 127.0.0.1:52373 (LISTEN)\n"
        )

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates(set())):
                with pytest.raises(ServerDiscoveryNotFoundError) as exc_info:
                    discover_local_opencode_server()

        assert exc_info.value.candidates_scanned == 2
        assert "none returned healthy" in str(exc_info.value)

    def test_bad_ambiguous_multiple_healthy(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Multiple healthy servers → ambiguous error."""
        lsof_output = (
            "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "opencode- 53530 user   12u  IPv4 0x2  0t0  TCP 127.0.0.1:52373 (LISTEN)\n"
        )

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates({52372, 52373})):
                with pytest.raises(ServerDiscoveryAmbiguousError) as exc_info:
                    discover_local_opencode_server()

        assert len(exc_info.value.healthy_endpoints) == 2
        assert "http://127.0.0.1:52372" in exc_info.value.healthy_endpoints
        assert "http://127.0.0.1:52373" in exc_info.value.healthy_endpoints

    def test_edge_auth_required_no_credentials(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: Candidate returns 401, no OPENCODE_SERVER_PASSWORD → auth required."""
        lsof_output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        monkeypatch.delenv("OPENCODE_SERVER_USERNAME", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates(set(), auth_required_ports={52372})):
                with pytest.raises(ServerAuthRequiredError) as exc_info:
                    discover_local_opencode_server()

        assert "OPENCODE_SERVER_PASSWORD" in str(exc_info.value)
        assert exc_info.value.target_url == "http://127.0.0.1:52372"

    def test_edge_auth_required_with_credentials_still_fails(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: Candidate returns 401 even with credentials → not auth error (just unhealthy)."""
        lsof_output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"

        # Set credentials — _resolve_auth() will return headers, so 401 is NOT classified as auth-required
        monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "secret")
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates(set(), auth_required_ports={52372})):
                with pytest.raises(ServerDiscoveryNotFoundError) as exc_info:
                    discover_local_opencode_server()

        # Should NOT be ServerAuthRequiredError since credentials are configured
        assert exc_info.value.candidates_scanned == 1

    def test_edge_windows_platform(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: Windows platform raises explicit unsupported platform error."""
        monkeypatch.setattr("governance_runtime.infrastructure.opencode_server_client.sys.platform", "win32")
        with pytest.raises(ServerDiscoveryUnsupportedPlatformError) as exc_info:
            discover_local_opencode_server()

        assert exc_info.value.platform == "win32"
        assert "not implemented on Windows" in str(exc_info.value)
        assert "--server-mode managed" in str(exc_info.value)

    def test_edge_linux_platform_not_blocked(self, monkeypatch: pytest.MonkeyPatch):
        """Edge: Linux platform proceeds with lsof (not blocked)."""
        lsof_output = "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"

        monkeypatch.setattr("governance_runtime.infrastructure.opencode_server_client.sys.platform", "linux")
        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates({52372})):
                base_url, health = discover_local_opencode_server()

        assert base_url == "http://127.0.0.1:52372"

    def test_corner_healthy_preferred_over_auth_required(self, monkeypatch: pytest.MonkeyPatch):
        """Corner: One healthy + one auth-required → returns the healthy one."""
        lsof_output = (
            "opencode- 53525 user   11u  IPv4 0x1  0t0  TCP 127.0.0.1:52372 (LISTEN)\n"
            "opencode- 53530 user   12u  IPv4 0x2  0t0  TCP 127.0.0.1:52373 (LISTEN)\n"
        )

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.subprocess.run", return_value=self._mock_lsof(lsof_output)):
            with patch(f"{self._MODULE}.urllib.request.urlopen",
                       side_effect=self._mock_urlopen_for_candidates(
                           {52372}, auth_required_ports={52373})):
                base_url, health = discover_local_opencode_server()

        assert base_url == "http://127.0.0.1:52372"
        assert health["healthy"] is True


# ---------------------------------------------------------------------------
# get_projects(), resolve_project_id(), get_active_session() project-based tests
# ---------------------------------------------------------------------------


class TestGetProjects:
    """Tests for get_projects() — GET /project."""

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def test_happy_returns_project_list(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Returns list of project dicts from server."""
        projects = [
            {"id": "proj_abc", "worktree": "/Users/user/work/repo1"},
            {"id": "proj_def", "worktree": "/Users/user/work/repo2"},
        ]

        def mock_urlopen(req, **kwargs):
            resp = MagicMock()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            resp.read.return_value = json.dumps(projects).encode()
            return resp

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
            result = get_projects(base_url="http://127.0.0.1:52372")

        assert result == projects

    def test_happy_threads_base_url(self, monkeypatch: pytest.MonkeyPatch):
        """Happy: Provided base_url is used for the request URL."""
        captured = {}

        def mock_urlopen(req, **kwargs):
            captured["url"] = req.full_url
            resp = MagicMock()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            resp.read.return_value = b"[]"
            return resp

        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.urllib.request.urlopen", side_effect=mock_urlopen):
            get_projects(base_url="http://127.0.0.1:52372")

        assert captured["url"] == "http://127.0.0.1:52372/project"

    def test_bad_server_unreachable(self, monkeypatch: pytest.MonkeyPatch):
        """Bad: Server unreachable raises APIError."""
        monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
        with patch(f"{self._MODULE}.urllib.request.urlopen",
                   side_effect=OSError("Connection refused")):
            with pytest.raises(APIError, match="Failed to get projects"):
                get_projects(base_url="http://127.0.0.1:52372")


class TestResolveProjectId:
    """Tests for resolve_project_id() — worktree path → project ID.

    Happy: Exact match and symlink-resolved match
    Bad: No matching project
    Corner: Trailing slashes, case sensitivity
    """

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def _mock_get_projects(self, projects: list[dict]):
        """Return a patcher for get_projects that returns fixed data."""
        return patch(f"{self._MODULE}.get_projects", return_value=projects)

    def test_happy_exact_worktree_match(self, tmp_path: Path):
        """Happy: Exact worktree path matches project."""
        repo = tmp_path / "repo"
        repo.mkdir()
        projects = [
            {"id": "proj_abc", "worktree": str(repo)},
            {"id": "proj_def", "worktree": "/other/path"},
        ]
        with self._mock_get_projects(projects):
            result = resolve_project_id(str(repo))
        assert result == "proj_abc"

    def test_happy_trailing_slash_normalized(self, tmp_path: Path):
        """Happy: Trailing slash in project_path is stripped before comparison."""
        repo = tmp_path / "repo"
        repo.mkdir()
        projects = [{"id": "proj_abc", "worktree": str(repo)}]
        with self._mock_get_projects(projects):
            result = resolve_project_id(str(repo) + "/")
        assert result == "proj_abc"

    def test_happy_symlink_resolved(self, tmp_path: Path):
        """Happy: Symlinked path resolves to same realpath as worktree."""
        repo = tmp_path / "repo"
        repo.mkdir()
        link = tmp_path / "repo-link"
        link.symlink_to(repo)
        projects = [{"id": "proj_abc", "worktree": str(repo)}]
        with self._mock_get_projects(projects):
            result = resolve_project_id(str(link))
        assert result == "proj_abc"

    def test_bad_no_matching_project(self, tmp_path: Path):
        """Bad: No project matches the given path → ProjectNotFoundError."""
        repo = tmp_path / "repo"
        repo.mkdir()
        projects = [
            {"id": "proj_abc", "worktree": "/some/other/repo"},
            {"id": "proj_def", "worktree": "/yet/another/repo"},
        ]
        with self._mock_get_projects(projects):
            with pytest.raises(ProjectNotFoundError) as exc_info:
                resolve_project_id(str(repo))
        assert exc_info.value.project_path == str(repo)
        assert "No OpenCode project found" in str(exc_info.value)

    def test_bad_empty_project_list(self, tmp_path: Path):
        """Bad: Server returns no projects → ProjectNotFoundError."""
        repo = tmp_path / "repo"
        repo.mkdir()
        with self._mock_get_projects([]):
            with pytest.raises(ProjectNotFoundError):
                resolve_project_id(str(repo))

    def test_corner_worktree_with_trailing_slash_in_server_data(self, tmp_path: Path):
        """Corner: Server returns worktree with trailing slash — still matches."""
        repo = tmp_path / "repo"
        repo.mkdir()
        projects = [{"id": "proj_abc", "worktree": str(repo) + "/"}]
        with self._mock_get_projects(projects):
            result = resolve_project_id(str(repo))
        assert result == "proj_abc"


class TestGetActiveSessionProjectResolution:
    """Tests for get_active_session() with project-based resolution.

    Happy: project_path → project_id → session match
    Bad: No project, no session for project
    Corner: Multiple sessions for same project, global sessions excluded
    Edge: No project_path (fallback to first session)
    """

    _MODULE = "governance_runtime.infrastructure.opencode_server_client"

    def _mock_sessions(self, sessions: list[dict]):
        return patch(f"{self._MODULE}.get_sessions", return_value=sessions)

    def _mock_project_id(self, project_id: str):
        return patch(f"{self._MODULE}.resolve_project_id", return_value=project_id)

    def _mock_project_not_found(self, project_path: str):
        return patch(
            f"{self._MODULE}.resolve_project_id",
            side_effect=ProjectNotFoundError(
                f"No project found for {project_path}", project_path=project_path,
            ),
        )

    def test_happy_single_session_for_project(self):
        """Happy: Exactly one session matches the project → returned."""
        sessions = [
            {"id": "ses_1", "projectID": "proj_abc", "title": "My Session", "time": {"created": 1000, "updated": 1000}},
            {"id": "ses_2", "projectID": "global", "title": "Global Session", "time": {"created": 900, "updated": 900}},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_id("proj_abc"):
                result = get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")
        assert result["id"] == "ses_1"
        assert result["projectID"] == "proj_abc"

    def test_happy_multiple_sessions_returns_most_recent(self):
        """Happy: Multiple sessions for project → returns most recently created."""
        sessions = [
            {"id": "ses_old", "projectID": "proj_abc", "title": "Old Session", "time": {"created": 900, "updated": 900}},
            {"id": "ses_new", "projectID": "proj_abc", "title": "New Session", "time": {"created": 2000, "updated": 2000}},
            {"id": "ses_mid", "projectID": "proj_abc", "title": "Mid Session", "time": {"created": 1500, "updated": 1500}},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_id("proj_abc"):
                result = get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")
        assert result["id"] == "ses_new"

    def test_happy_excludes_global_sessions(self):
        """Happy: Global sessions (projectID='global') don't match a repo project."""
        sessions = [
            {"id": "ses_global", "projectID": "global", "title": "Global", "time": {"created": 2000, "updated": 2000}},
            {"id": "ses_repo", "projectID": "proj_abc", "title": "Repo Session", "time": {"created": 1000, "updated": 1000}},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_id("proj_abc"):
                result = get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")
        assert result["id"] == "ses_repo"

    def test_bad_project_not_found(self):
        """Bad: No project matches path → ProjectNotFoundError propagates."""
        sessions = [
            {"id": "ses_1", "projectID": "proj_abc", "title": "Some Session"},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_not_found("/Users/user/work/unknown"):
                with pytest.raises(ProjectNotFoundError) as exc_info:
                    get_active_session("/Users/user/work/unknown", base_url="http://127.0.0.1:52372")
        assert exc_info.value.project_path == "/Users/user/work/unknown"

    def test_bad_no_session_for_project(self):
        """Bad: Project exists but no sessions for it → ProjectSessionNotFoundError."""
        sessions = [
            {"id": "ses_1", "projectID": "proj_other", "title": "Other Project Session"},
            {"id": "ses_2", "projectID": "global", "title": "Global Session"},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_id("proj_abc"):
                with pytest.raises(ProjectSessionNotFoundError) as exc_info:
                    get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")
        assert exc_info.value.project_id == "proj_abc"
        assert exc_info.value.project_path == "/Users/user/work/repo"

    def test_bad_no_sessions_at_all(self):
        """Bad: Server returns zero sessions → APIError."""
        with self._mock_sessions([]):
            with pytest.raises(APIError, match="No OpenCode sessions found"):
                get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")

    def test_edge_no_project_path_returns_first_session(self):
        """Edge: No project_path → returns first session (no project resolution)."""
        sessions = [
            {"id": "ses_1", "projectID": "global", "title": "First Session"},
            {"id": "ses_2", "projectID": "proj_abc", "title": "Second Session"},
        ]
        with self._mock_sessions(sessions):
            result = get_active_session(base_url="http://127.0.0.1:52372")
        assert result["id"] == "ses_1"

    def test_edge_only_global_sessions_for_repo_project(self):
        """Edge: All sessions are global, none match the repo project → ProjectSessionNotFoundError."""
        sessions = [
            {"id": "ses_1", "projectID": "global", "title": "Global 1"},
            {"id": "ses_2", "projectID": "global", "title": "Global 2"},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_id("proj_abc"):
                with pytest.raises(ProjectSessionNotFoundError):
                    get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")

    def test_happy_threads_base_url_to_resolve_project_id(self):
        """Happy: base_url is threaded through to resolve_project_id."""
        sessions = [
            {"id": "ses_1", "projectID": "proj_abc", "title": "Session"},
        ]
        captured = {}

        def mock_resolve_project(project_path, *, base_url=None):
            captured["base_url"] = base_url
            return "proj_abc"

        with self._mock_sessions(sessions):
            with patch(f"{self._MODULE}.resolve_project_id", side_effect=mock_resolve_project):
                get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")

        assert captured["base_url"] == "http://127.0.0.1:52372"

    def test_happy_threads_directory_to_get_sessions(self):
        """Happy: project_path is forwarded as directory= to get_sessions()."""
        sessions = [
            {"id": "ses_1", "projectID": "proj_abc", "title": "Session"},
        ]
        captured = {}

        def mock_get_sessions(*, base_url=None, directory=None):
            captured["directory"] = directory
            return sessions

        with patch(f"{self._MODULE}.get_sessions", side_effect=mock_get_sessions):
            with self._mock_project_id("proj_abc"):
                get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")

        assert captured["directory"] == "/Users/user/work/repo"

    def test_edge_no_project_path_passes_none_directory(self):
        """Edge: No project_path → directory=None passed to get_sessions()."""
        sessions = [
            {"id": "ses_1", "projectID": "global", "title": "Global Session"},
        ]
        captured = {}

        def mock_get_sessions(*, base_url=None, directory=None):
            captured["directory"] = directory
            return sessions

        with patch(f"{self._MODULE}.get_sessions", side_effect=mock_get_sessions):
            result = get_active_session(base_url="http://127.0.0.1:52372")

        assert captured["directory"] is None
        assert result["id"] == "ses_1"

    def test_bad_no_session_diagnostic_includes_actual_project_ids(self):
        """Bad: Error message includes actual projectIDs for debugging."""
        sessions = [
            {"id": "ses_1", "projectID": "proj_other", "title": "Other"},
            {"id": "ses_2", "projectID": "global", "title": "Global"},
        ]
        with self._mock_sessions(sessions):
            with self._mock_project_id("proj_abc"):
                with pytest.raises(ProjectSessionNotFoundError, match="proj_other"):
                    get_active_session("/Users/user/work/repo", base_url="http://127.0.0.1:52372")
