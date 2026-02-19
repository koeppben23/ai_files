"""Tests for model identity module."""

from __future__ import annotations

import pytest

from governance.domain.model_identity import (
    ModelIdentity,
    infer_context_limit,
    validate_model_identity,
)


@pytest.mark.governance
class TestModelIdentity:
    def test_creates_identity_with_required_fields(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus-20240229",
            context_limit=200000,
        )
        
        assert identity.provider == "anthropic"
        assert identity.model_id == "claude-3-opus-20240229"
        assert identity.context_limit == 200000
        assert identity.temperature == 0.0
    
    def test_creates_identity_with_all_fields(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus-20240229",
            context_limit=200000,
            temperature=0.7,
            version="20240229",
            quantization="4bit",
            deployment_id="my-deployment",
        )
        
        assert identity.temperature == 0.7
        assert identity.version == "20240229"
        assert identity.quantization == "4bit"
        assert identity.deployment_id == "my-deployment"
    
    def test_to_dict(self):
        identity = ModelIdentity(
            provider="openai",
            model_id="gpt-4-turbo",
            context_limit=128000,
            temperature=0.0,
        )
        
        data = identity.to_dict()
        
        assert data["provider"] == "openai"
        assert data["model_id"] == "gpt-4-turbo"
        assert data["context_limit"] == 128000
        assert "version" not in data  # Optional fields not included if None
    
    def test_from_dict(self):
        data = {
            "provider": "google",
            "model_id": "gemini-1.5-pro",
            "context_limit": 1048576,
            "temperature": 0.5,
        }
        
        identity = ModelIdentity.from_dict(data)
        
        assert identity.provider == "google"
        assert identity.model_id == "gemini-1.5-pro"
        assert identity.context_limit == 1048576
    
    def test_compute_hash_is_deterministic(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus",
            context_limit=200000,
        )
        
        hash1 = identity.compute_hash()
        hash2 = identity.compute_hash()
        
        assert hash1 == hash2
        assert len(hash1) == 16
    
    def test_different_identities_have_different_hashes(self):
        id1 = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus",
            context_limit=200000,
        )
        
        id2 = ModelIdentity(
            provider="openai",
            model_id="gpt-4-turbo",
            context_limit=128000,
        )
        
        assert id1.compute_hash() != id2.compute_hash()


@pytest.mark.governance
class TestInferContextLimit:
    def test_infers_claude_context_limit(self):
        limit = infer_context_limit("claude-3-opus-20240229")
        assert limit == 200000
    
    def test_infers_gpt4_context_limit(self):
        limit = infer_context_limit("gpt-4-turbo-preview")
        assert limit == 128000
    
    def test_infers_gemini_context_limit(self):
        limit = infer_context_limit("gemini-1.5-pro-latest")
        assert limit == 1048576
    
    def test_returns_zero_for_unknown(self):
        limit = infer_context_limit("unknown-model-xyz")
        assert limit == 0


@pytest.mark.governance
class TestValidateModelIdentity:
    def test_validates_complete_identity(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus",
            context_limit=200000,
        )
        
        valid, reason = validate_model_identity(identity)
        
        assert valid is True
        assert reason == "OK"
    
    def test_rejects_missing_provider(self):
        identity = ModelIdentity(
            provider="",
            model_id="claude-3-opus",
            context_limit=200000,
        )
        
        valid, reason = validate_model_identity(identity)
        
        assert valid is False
        assert reason == "MISSING_PROVIDER"
    
    def test_rejects_missing_model_id(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="",
            context_limit=200000,
        )
        
        valid, reason = validate_model_identity(identity)
        
        assert valid is False
        assert reason == "MISSING_MODEL_ID"
    
    def test_rejects_invalid_temperature(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus",
            context_limit=200000,
            temperature=3.0,  # Invalid
        )
        
        valid, reason = validate_model_identity(identity)
        
        assert valid is False
        assert reason == "INVALID_TEMPERATURE"
    
    def test_accepts_zero_context_limit_if_inferrable(self):
        identity = ModelIdentity(
            provider="anthropic",
            model_id="claude-3-opus",  # Can infer from this
            context_limit=0,
        )
        
        valid, reason = validate_model_identity(identity)
        
        # Should pass because we can infer the limit
        assert valid is True
