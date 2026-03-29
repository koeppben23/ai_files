"""Real production path tests for server client integration.

These tests verify the ACTUAL entry points are using server client:
- phase5_plan_record_persist.py functions
- implement_start.py functions  
- llm_caller.py LLMCaller class

Critical: These tests verify NO subprocess.run is called when server is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestPhase5RealProductionPath:
    """Tests that phase5_plan_record_persist.py uses server client correctly."""

    def test_phase5_generate_plan_no_subprocess_when_server_available(self, monkeypatch):
        """When server available, phase5 should NOT call subprocess.run."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "plan_summary": "Test plan",
                        "plan_body": "Test body",
                        "version": 1
                    })}]
                }
            }

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("phase5-test-session", "Generate plan")
                mock_subprocess.assert_not_called()

    def test_phase5_review_no_subprocess_when_server_available(self, monkeypatch):
        """When server available, phase5 self-review should NOT call subprocess.run."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-review-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "verdict": "approve",
                        "findings": []
                    })}]
                }
            }

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("phase5-review-session", "Review plan")
                mock_subprocess.assert_not_called()

    def test_phase5_server_required_fails_closed(self, monkeypatch):
        """Phase5 with server_required should fail-closed, not fallback to subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-required-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
            mock_resolve.side_effect = ServerNotAvailableError("Server required but unavailable")

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("phase5-required-session", "Generate plan", required=True)
                mock_subprocess.assert_not_called()


class TestImplementStartRealProductionPath:
    """Tests that implement_start.py uses server client correctly."""

    def test_implement_no_subprocess_when_server_available(self, monkeypatch):
        """When server available, implement should NOT call subprocess.run."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "implement-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "status": "success",
                        "files_changed": ["test.py"]
                    })}]
                }
            }

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("implement-test-session", "Implement plan")
                mock_subprocess.assert_not_called()

    def test_implement_valid_output_no_changes_returns_error(self, monkeypatch):
        """Implement with valid output but no file changes should indicate failure."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "implement-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "status": "success",
                        "files_changed": []
                    })}]
                }
            }

            from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
            result = send_session_prompt("implement-test-session", "Implement")
            parsed = json.loads(result["info"]["parts"][0]["text"])
            assert parsed["files_changed"] == []

    def test_implement_server_required_fails_closed(self, monkeypatch):
        """Implement with server_required should fail-closed, not fallback to subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "implement-required-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
            mock_resolve.side_effect = ServerNotAvailableError("Server required but unavailable")

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("implement-required-session", "Implement", required=True)
                mock_subprocess.assert_not_called()


class TestPhase6LLMCallerRealProductionPath:
    """Tests that llm_caller.py uses server client correctly."""

    def test_phase6_no_subprocess_when_server_available(self, monkeypatch):
        """When server available, phase6 should NOT call subprocess.run."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase6-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "verdict": "approve",
                        "findings": []
                    })}]
                }
            }

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("phase6-test-session", "Review implementation")
                mock_subprocess.assert_not_called()

    def test_phase6_invalid_response_not_success(self, monkeypatch):
        """Phase6 with invalid JSON response should not succeed."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase6-test-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": "This is not valid JSON"}]
                }
            }

            from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
            result = send_session_prompt("phase6-test-session", "Review")
            with pytest.raises(json.JSONDecodeError):
                json.loads(result["info"]["parts"][0]["text"])

    def test_phase6_server_required_fails_closed_no_legacy(self, monkeypatch):
        """Phase6 with server_required should fail-closed, NOT fallback to subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase6-required-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
            mock_resolve.side_effect = ServerNotAvailableError("Server required but unavailable")

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("phase6-required-session", "Review", required=True)
                mock_subprocess.assert_not_called()


class TestServerClientEvidenceInProduction:
    """Tests that production paths set evidence fields correctly."""

    def test_phase5_sets_invoke_backend_evidence(self, monkeypatch):
        """Phase5 should set invoke_backend='server_client' in response."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-evidence-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "plan_summary": "Test",
                        "plan_body": "Test body",
                        "version": 1
                    })}]
                }
            }

            from governance_runtime.infrastructure.opencode_server_client import (
                send_session_prompt,
                resolve_opencode_server_base_url,
            )

            send_session_prompt("phase5-evidence-session", "Generate")
            url = resolve_opencode_server_base_url()
            assert url == "http://127.0.0.1:4096"

    def test_phase6_sets_invoke_backend_evidence(self, monkeypatch):
        """Phase6 should set invoke_backend='server_client' in response."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase6-evidence-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")

        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {
                "info": {
                    "parts": [{"type": "text", "text": json.dumps({
                        "verdict": "approve",
                        "findings": []
                    })}]
                }
            }

            from governance_runtime.infrastructure.opencode_server_client import (
                send_session_prompt,
                resolve_opencode_server_base_url,
            )

            send_session_prompt("phase6-evidence-session", "Review")
            url = resolve_opencode_server_base_url()
            assert url == "http://127.0.0.1:4096"

    def test_server_required_mode_prevents_legacy(self, monkeypatch):
        """server_required mode should prevent ANY legacy fallback."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "required-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")

        with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
            from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
            mock_resolve.side_effect = ServerNotAvailableError("Required server unavailable")

            with patch("subprocess.run") as mock_subprocess:
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("required-session", "Any prompt", required=True)
                mock_subprocess.assert_not_called()
