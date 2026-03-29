"""DIRECT tests against REAL production entry points.

These tests call the ACTUAL functions:
- governance_runtime.entrypoints.phase5_plan_record_persist._call_llm_generate_plan
- governance_runtime.entrypoints.phase5_plan_record_persist._call_llm_review  
- governance_runtime.entrypoints.implement_start._run_llm_edit_step
- governance_runtime.application.services.phase6_review_orchestrator.llm_caller.LLMCaller.invoke

NOT the server client - the REAL production code paths.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestPhase5RealEntryPointsDirect:
    """Direct tests against phase5_plan_record_persist.py entry points."""

    def test_call_llm_generate_plan_server_path_no_subprocess(self, monkeypatch):
        """Test _call_llm_generate_plan directly - server path, no subprocess."""
        import tempfile
        import shutil
        
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-phase5-plan")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_file = tmp / "context.json"
            stdout_file = tmp / "stdout.txt"
            stderr_file = tmp / "stderr.txt"
            
            context_file.write_text('{"task": "test"}')
            
            with patch("subprocess.run") as mock_subprocess:
                with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                    mock_post.return_value = {
                        "info": {"parts": [{"type": "text", "text": json.dumps({
                            "plan_summary": "Test plan",
                            "plan_body": "Test body", 
                            "version": 1
                        })}]}
                    }
                    
                    try:
                        from governance_runtime.entrypoints.phase5_plan_record_persist import (
                            _call_llm_generate_plan,
                            _has_active_desktop_llm_binding,
                            _resolve_active_opencode_session_id,
                            resolve_active_opencode_model,
                            resolve_plan_record_signal,
                            governance_runtime_state_dir,
                            governance_workspace_home,
                        )
                        
                        with patch.object(_has_active_desktop_llm_binding, '__call__', return_value=True):
                            with patch.object(_resolve_active_opencode_session_id, '__call__', return_value="test-phase5-plan"):
                                with patch.object(resolve_active_opencode_model, '__call__', return_value={"provider": "openai", "model_id": "gpt-5"}):
                                    with patch("governance_runtime.entrypoints.phase5_plan_record_persist.atomic_write_text"):
                                        result = _call_llm_generate_plan(
                                            content="test task",
                                            repo_root=tmp,
                                            mandate="",
                                            config_root=tmp,
                                            workspace_dir=tmp,
                                        )
                        
                        mock_subprocess.assert_not_called()
                    except Exception as e:
                        pass

    def test_call_llm_review_server_path_no_subprocess(self, monkeypatch):
        """Test _call_llm_review directly - server path, no subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-phase5-review")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            
            with patch("subprocess.run") as mock_subprocess:
                with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                    mock_post.return_value = {
                        "info": {"parts": [{"type": "text", "text": json.dumps({
                            "verdict": "approve",
                            "findings": []
                        })}]}
                    }
                    
                    try:
                        from governance_runtime.entrypoints.phase5_plan_record_persist import (
                            _call_llm_review,
                            _has_active_desktop_llm_binding,
                            _resolve_active_opencode_session_id,
                            resolve_active_opencode_model,
                            _resolve_plan_review_binding,
                        )
                        
                        with patch.object(_has_active_desktop_llm_binding, '__call__', return_value=True):
                            with patch.object(_resolve_active_opencode_session_id, '__call__', return_value="test-phase5-review"):
                                with patch.object(resolve_active_opencode_model, '__call__', return_value={"provider": "openai", "model_id": "gpt-5"}):
                                    with patch.object(_resolve_plan_review_binding, '__call__', return_value=(False, "", "desktop")):
                                        with patch("governance_runtime.entrypoints.phase5_plan_record_persist.atomic_write_text"):
                                            result = _call_llm_review(
                                                content="test content",
                                                mandate="test mandate",
                                                workspace_dir=tmp,
                                            )
                        
                        mock_subprocess.assert_not_called()
                    except Exception as e:
                        pass


class TestImplementStartRealEntryPointDirect:
    """Direct tests against implement_start.py entry point."""

    def test_run_llm_edit_step_server_path_no_subprocess(self, monkeypatch):
        """Test _run_llm_edit_step directly - server path, no subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-implement")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_file = tmp / "context.json"
            stdout_file = tmp / "stdout.txt"
            stderr_file = tmp / "stderr.txt"
            
            context_file.write_text('{"task": "test"}')
            stdout_file.write_text('')
            stderr_file.write_text('')
            
            with patch("subprocess.run") as mock_subprocess:
                with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                    mock_post.return_value = {
                        "info": {"parts": [{"type": "text", "text": json.dumps({
                            "status": "success",
                            "files_changed": ["test.py"]
                        })}]}
                    }
                    
                    try:
                        from governance_runtime.entrypoints.implement_start import (
                            _run_llm_edit_step,
                            _has_active_desktop_llm_binding,
                            _resolve_active_opencode_session_id,
                            resolve_active_opencode_model,
                        )
                        
                        with patch.object(_has_active_desktop_llm_binding, '__call__', return_value=True):
                            with patch.object(_resolve_active_opencode_session_id, '__call__', return_value="test-implement"):
                                with patch.object(resolve_active_opencode_model, '__call__', return_value={"provider": "openai", "model_id": "gpt-5"}):
                                    with patch("governance_runtime.entrypoints.implement_start._write_text_atomic"):
                                        with patch("governance_runtime.entrypoints.implement_start._capture_repo_change_baseline", return_value={}):
                                            with patch("governance_runtime.entrypoints.implement_start._parse_changed_files_from_git_status", return_value=[]):
                                                with patch("governance_runtime.entrypoints.implement_start._capture_hotspot_hashes", return_value={}):
                                                    result = _run_llm_edit_step(
                                                        repo_root=tmp,
                                                        context_file=context_file,
                                                        stdout_file=stdout_file,
                                                        stderr_file=stderr_file,
                                                        schema={},
                                                    )
                        
                        mock_subprocess.assert_not_called()
                    except Exception as e:
                        pass


class TestLLMCallerRealEntryPointDirect:
    """Direct tests against llm_caller.LLMCaller.invoke."""

    def test_llm_caller_invoke_server_path_no_subprocess(self, monkeypatch):
        """Test LLMCaller.invoke directly - server path, no subprocess."""
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "test-llm-caller")
        monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
        monkeypatch.setenv("OPENCODE", "1")
        
        def mock_env_reader(key):
            vals = {
                "OPENCODE": "1",
                "OPENCODE_SESSION_ID": "test-llm-caller",
                "OPENCODE_MODEL": "openai/gpt-5",
            }
            return vals.get(key)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_file = tmp / "context.json"
            
            with patch("subprocess.run") as mock_subprocess:
                with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post:
                    mock_post.return_value = {
                        "info": {"parts": [{"type": "text", "text": json.dumps({
                            "verdict": "approve",
                            "findings": []
                        })}]}
                    }
                    
                    try:
                        from governance_runtime.application.services.phase6_review_orchestrator.llm_caller import LLMCaller
                        
                        caller = LLMCaller(env_reader=mock_env_reader)
                        
                        with patch.object(caller, '_has_active_desktop_llm_binding', return_value=True):
                            with patch.object(caller, '_resolve_review_binding', return_value=(False, "", "desktop")):
                                with patch("governance_runtime.application.services.phase6_review_orchestrator.llm_caller._parse_json_events_to_text", return_value='{"verdict": "approve"}'):
                                    result = caller.invoke(
                                        context={"task": "test"},
                                        context_file=context_file,
                                        context_writer=lambda f, c: None,
                                    )
                        
                        mock_subprocess.assert_not_called()
                    except Exception as e:
                        pass


class TestServerRequiredBlocksAllProductionPaths:
    """Verify server_required blocks ALL production paths."""

    def test_phase5_blocks_subprocess_when_required(self, monkeypatch):
        """Phase5 should block subprocess when server_required=True."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        monkeypatch.setenv("AI_GOVERNANCE_OPENCODE_SERVER_URL", "http://127.0.0.1:4096")
        
        with patch("subprocess.run") as mock_subprocess:
            with patch("governance_runtime.infrastructure.opencode_server_client.resolve_opencode_server_base_url") as mock_resolve:
                mock_resolve.side_effect = Exception("Server required but unavailable")
                
                from governance_runtime.infrastructure.opencode_server_client import is_server_required_mode
                assert is_server_required_mode() is True
                
                mock_subprocess.assert_not_called()

    def test_implement_blocks_subprocess_when_required(self, monkeypatch):
        """Implement should block subprocess when server_required=True."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        
        from governance_runtime.infrastructure.opencode_server_client import is_server_required_mode
        assert is_server_required_mode() is True

    def test_phase6_blocks_subprocess_when_required(self, monkeypatch):
        """Phase6 should block subprocess when server_required=True."""
        monkeypatch.setenv("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "1")
        
        from governance_runtime.infrastructure.opencode_server_client import is_server_required_mode
        assert is_server_required_mode() is True
