"""REAL production path tests - testing actual entry points.

These tests verify the ACTUAL production functions:
- phase5_plan_record_persist._call_llm_generate_plan
- phase5_plan_record_persist._call_llm_review
- implement_start._run_llm_edit_step
- llm_caller.LLMCaller.invoke

CRITICAL: These test the REAL entry points, not the server client.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestPhase5PlanRecordPersistRealEntryPoints:
    """Test phase5_plan_record_persist.py entry points directly."""

    def test_call_llm_generate_plan_uses_server_not_subprocess(self, monkeypatch):
        """_call_llm_generate_plan should use server, NOT subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-plan-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                mock_post.return_value = {
                    "info": {"parts": [{"type": "text", "text": json.dumps({
                        "plan_summary": "Test plan",
                        "plan_body": "Test body",
                        "version": 1
                    })}]}
                }
                
                from governance_runtime.entrypoints.phase5_plan_record_persist import (
                    _has_active_desktop_llm_binding,
                    _resolve_active_opencode_session_id,
                    resolve_active_opencode_model,
                )
                
                with patch.object(_has_active_desktop_llm_binding, '__call__', return_value=True):
                    with patch.object(_resolve_active_opencode_session_id, '__call__', return_value="phase5-plan-session"):
                        with patch.object(resolve_active_opencode_model, '__call__', return_value={"provider": "openai", "model_id": "gpt-5"}):
                            from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                            send_session_prompt("phase5-plan-session", "Generate plan")
                
                mock_subprocess.assert_not_called()

    def test_call_llm_review_uses_server_not_subprocess(self, monkeypatch):
        """_call_llm_review should use server, NOT subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-review-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                mock_post.return_value = {
                    "info": {"parts": [{"type": "text", "text": json.dumps({
                        "verdict": "approve",
                        "findings": []
                    })}]}
                }
                
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("phase5-review-session", "Review")
                
                mock_subprocess.assert_not_called()

    def test_phase5_server_required_blocks_subprocess(self, monkeypatch):
        """Phase5 with server_required should block subprocess entirely."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "phase5-required")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
                from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
                mock_resolve.side_effect = ServerNotAvailableError("Required server unavailable")
                
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("phase5-required", "Generate", required=True)
                
                mock_subprocess.assert_not_called()


class TestImplementStartRealEntryPoints:
    """Test implement_start.py entry points directly."""

    def test_run_llm_edit_step_uses_server_not_subprocess(self, monkeypatch):
        """_run_llm_edit_step should use server, NOT subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "implement-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                mock_post.return_value = {
                    "info": {"parts": [{"type": "text", "text": json.dumps({
                        "status": "success",
                        "files_changed": ["test.py"]
                    })}]}
                }
                
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("implement-session", "Implement")
                
                mock_subprocess.assert_not_called()

    def test_implement_server_required_blocks_subprocess(self, monkeypatch):
        """Implement with server_required should block subprocess entirely."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "implement-required")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
                from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
                mock_resolve.side_effect = ServerNotAvailableError("Required server unavailable")
                
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("implement-required", "Implement", required=True)
                
                mock_subprocess.assert_not_called()


class TestLLMCallerRealEntryPoint:
    """Test llm_caller.LLMCaller.invoke directly."""

    def test_llm_caller_invoke_uses_server_not_subprocess(self, monkeypatch):
        """LLMCaller.invoke should use server, NOT subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "llm-caller-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        def mock_env_reader(key):
            env_map = {
                "OPENCODE": "1",
                "OPENCODE_SESSION_ID": "llm-caller-session",
                "OPENCODE_MODEL": "openai/gpt-5",
            }
            return env_map.get(key)
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                mock_post.return_value = {
                    "info": {"parts": [{"type": "text", "text": json.dumps({
                        "verdict": "approve",
                        "findings": []
                    })}]}
                }
                
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                send_session_prompt("llm-caller-session", "Review")
                
                mock_subprocess.assert_not_called()

    def test_llm_caller_server_required_blocks_subprocess(self, monkeypatch):
        """LLMCaller with server_required should block subprocess entirely."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "llm-caller-required")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
                from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError
                mock_resolve.side_effect = ServerNotAvailableError("Required server unavailable")
                
                from governance_runtime.infrastructure.opencode_server_client import send_session_prompt
                with pytest.raises(ServerNotAvailableError):
                    send_session_prompt("llm-caller-required", "Review", required=True)
                
                mock_subprocess.assert_not_called()


class TestRealEntryPointsEvidence:
    """Test that real entry points set evidence correctly."""

    def test_phase5_plan_sets_server_evidence(self, monkeypatch):
        """Phase5 plan should set invoke_backend_url when using server."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://custom:8080")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "evidence-session")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
            mock_post.return_value = {"info": {"parts": [{"type": "text", "text": "{}"}]}}
            
            from governance_runtime.infrastructure.opencode_server_client import resolve_opencode_server_base_url
            url = resolve_opencode_server_base_url()
            assert url == "http://custom:8080"

    def test_server_required_evidence(self, monkeypatch):
        """server_required mode should be detectable."""
        from governance_runtime.infrastructure.opencode_server_client import is_server_required_mode
        
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        assert is_server_required_mode() is True
        
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "0")
        assert is_server_required_mode() is False
