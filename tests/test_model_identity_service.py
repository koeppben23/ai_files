"""Tests for model identity resolution service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.infrastructure.model_identity_service import (
    resolve_model_identity,
    ModelIdentityResolutionResult,
)
from governance.domain.model_identity import ModelIdentity, TrustLevel
from governance.domain.reason_codes import (
    BLOCKED_MODEL_CONTEXT_LIMIT_REQUIRED,
    BLOCKED_MODEL_IDENTITY_UNTRUSTED,
)


@pytest.mark.governance
class TestResolveModelIdentity:
    def test_pipeline_mode_blocks_missing_context_limit(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENCODE_MODEL_PROVIDER", raising=False)
        monkeypatch.delenv("OPENCODE_MODEL_ID", raising=False)
        
        result = resolve_model_identity(
            mode="pipeline",
            workspaces_home=tmp_path,
        )
        
        assert result.blocked is True
        assert result.reason_code == BLOCKED_MODEL_CONTEXT_LIMIT_REQUIRED
        assert result.identity is None
    
    def test_pipeline_mode_blocks_process_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.delenv("OPENCODE_BINDING_FILE", raising=False)
        
        result = resolve_model_identity(
            mode="pipeline",
            workspaces_home=tmp_path,
        )
        
        assert result.blocked is True
        assert result.reason_code == BLOCKED_MODEL_IDENTITY_UNTRUSTED
        msg = result.reason_message
        assert msg is not None
        assert "trusted source" in msg
    
    def test_pipeline_mode_accepts_binding_env(self, monkeypatch, tmp_path):
        binding_file = tmp_path / "governance.paths.json"
        binding_file.write_text("{}")
        
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.setenv("OPENCODE_BINDING_FILE", str(binding_file))
        
        result = resolve_model_identity(
            mode="pipeline",
            workspaces_home=tmp_path,
        )
        
        assert result.blocked is False
        assert result.identity is not None
        assert result.identity.source == "binding_env"
        assert result.identity.is_trusted_for_audit() is True
    
    def test_user_mode_accepts_process_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.delenv("OPENCODE_BINDING_FILE", raising=False)
        
        result = resolve_model_identity(
            mode="user",
            workspaces_home=tmp_path,
        )
        
        assert result.blocked is False
        assert result.identity is not None
        assert result.identity.source == "process_env"
        assert result.identity.is_trusted_for_audit() is False
    
    def test_writes_resolution_event(self, monkeypatch, tmp_path):
        binding_file = tmp_path / "governance.paths.json"
        binding_file.write_text("{}")
        
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.setenv("OPENCODE_BINDING_FILE", str(binding_file))
        
        result = resolve_model_identity(
            mode="user",
            workspaces_home=tmp_path,
        )
        
        assert result.event_path is not None
        assert result.event_path.exists()
        
        with open(result.event_path, "r") as f:
            event = json.load(f)
        
        assert event["schema"] == "opencode.model-identity-resolved.v1"
        assert event["eventType"] == "MODEL_IDENTITY_RESOLVED"
        assert event["identity"]["provider"] == "anthropic"
        assert event["isTrustedForAudit"] is True
    
    def test_precedence_chain_records_winner(self, monkeypatch, tmp_path):
        binding_file = tmp_path / "governance.paths.json"
        binding_file.write_text("{}")
        
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.setenv("OPENCODE_BINDING_FILE", str(binding_file))
        
        result = resolve_model_identity(
            mode="user",
            workspaces_home=tmp_path,
        )
        
        assert len(result.precedence_chain) == 1
        assert result.precedence_chain[0]["source"] == "binding_env"
        assert result.precedence_chain[0]["winner"] is True
    
    def test_require_trusted_for_audit_blocks_process_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.delenv("OPENCODE_BINDING_FILE", raising=False)
        
        result = resolve_model_identity(
            mode="user",
            workspaces_home=tmp_path,
            require_trusted_for_audit=True,
        )
        
        assert result.blocked is True
        assert result.reason_code == BLOCKED_MODEL_IDENTITY_UNTRUSTED
    
    def test_architect_mode_accepts_process_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.delenv("OPENCODE_BINDING_FILE", raising=False)
        
        result = resolve_model_identity(
            mode="architect",
            workspaces_home=tmp_path,
        )
        
        assert result.blocked is False
        assert result.identity is not None
    
    def test_implement_mode_accepts_process_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENCODE_MODEL_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENCODE_MODEL_ID", "claude-3-opus")
        monkeypatch.setenv("OPENCODE_MODEL_CONTEXT_LIMIT", "200000")
        monkeypatch.delenv("OPENCODE_BINDING_FILE", raising=False)
        
        result = resolve_model_identity(
            mode="implement",
            workspaces_home=tmp_path,
        )
        
        assert result.blocked is False
        assert result.identity is not None
