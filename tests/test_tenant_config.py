"""Tests for governance/infrastructure/tenant_config.py."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.governance
def test_load_tenant_config_returns_none_when_env_not_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config returns None when OPENCODE_TENANT_CONFIG is not set."""
    monkeypatch.delenv("OPENCODE_TENANT_CONFIG", raising=False)
    from governance.infrastructure.tenant_config import load_tenant_config
    assert load_tenant_config() is None


@pytest.mark.governance
def test_load_tenant_config_returns_none_when_file_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config returns None when file does not exist."""
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(tmp_path / "nonexistent.yaml"))
    from governance.infrastructure.tenant_config import load_tenant_config
    assert load_tenant_config() is None


@pytest.mark.governance
def test_load_tenant_config_returns_none_when_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config returns None when file contains invalid JSON."""
    config_file = tmp_path / "tenant.yaml"
    config_file.write_text("{ invalid json }")
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(config_file))
    from governance.infrastructure.tenant_config import load_tenant_config
    assert load_tenant_config() is None


@pytest.mark.governance
def test_load_tenant_config_returns_none_when_missing_required_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config returns None when required fields are missing."""
    config_file = tmp_path / "tenant.yaml"
    config_file.write_text(json.dumps({"version": "1.0.0"}))
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(config_file))
    from governance.infrastructure.tenant_config import load_tenant_config
    assert load_tenant_config() is None


@pytest.mark.governance
def test_load_tenant_config_returns_none_when_wrong_schema_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config returns None when schema version doesn't match."""
    config_file = tmp_path / "tenant.yaml"
    config_file.write_text(json.dumps({
        "version": "99.99.99",
        "tenant_id": "test-tenant",
        "default_profile": "profile.python-safety",
    }))
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(config_file))
    from governance.infrastructure.tenant_config import load_tenant_config
    assert load_tenant_config() is None


@pytest.mark.governance
def test_load_tenant_config_parses_valid_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config returns TenantConfig when config is valid."""
    config_file = tmp_path / "tenant.yaml"
    config_file.write_text(json.dumps({
        "version": "1.0.0",
        "tenant_id": "acme-corp",
        "default_profile": "profile.python-safety",
        "allowed_addons": ["addon1", "addon2"],
        "blocked_addons": ["addon3"],
        "audit_verbosity": "verbose",
    }))
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(config_file))
    from governance.infrastructure.tenant_config import load_tenant_config
    config = load_tenant_config()
    assert config is not None
    assert config.tenant_id == "acme-corp"
    assert config.default_profile == "profile.python-safety"
    assert config.allowed_addons == ("addon1", "addon2")
    assert config.blocked_addons == ("addon3",)
    assert config.audit_verbosity == "verbose"


@pytest.mark.governance
def test_load_tenant_config_defaults_optional_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """load_tenant_config uses defaults for optional fields."""
    config_file = tmp_path / "tenant.yaml"
    config_file.write_text(json.dumps({
        "version": "1.0.0",
        "tenant_id": "acme-corp",
        "default_profile": "profile.python-safety",
    }))
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(config_file))
    from governance.infrastructure.tenant_config import load_tenant_config
    config = load_tenant_config()
    assert config is not None
    assert config.allowed_addons == ()
    assert config.blocked_addons == ()
    assert config.audit_verbosity == "standard"


@pytest.mark.governance
def test_get_default_profile_returns_profile_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """get_default_profile returns profile ID from tenant config."""
    config_file = tmp_path / "tenant.yaml"
    config_file.write_text(json.dumps({
        "version": "1.0.0",
        "tenant_id": "acme-corp",
        "default_profile": "profile.python-safety",
    }))
    monkeypatch.setenv("OPENCODE_TENANT_CONFIG", str(config_file))
    from governance.infrastructure.tenant_config import get_default_profile
    assert get_default_profile() == "python-safety"


@pytest.mark.governance
def test_get_default_profile_returns_none_without_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """get_default_profile returns None when no tenant config."""
    monkeypatch.delenv("OPENCODE_TENANT_CONFIG", raising=False)
    from governance.infrastructure.tenant_config import get_default_profile
    assert get_default_profile() is None


@pytest.mark.governance
def test_tenant_config_schema_validates(tmp_path: Path):
    """Tenant config schema is valid JSON Schema."""
    import jsonschema
    schema_path = REPO_ROOT / "schemas" / "tenant_config.schema.json"
    schema = json.loads(schema_path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.governance
def test_tenant_config_validates_against_schema(tmp_path: Path):
    """Valid tenant config passes schema validation."""
    import jsonschema
    schema_path = REPO_ROOT / "schemas" / "tenant_config.schema.json"
    schema = json.loads(schema_path.read_text())
    validator = jsonschema.Draft202012Validator(schema)

    valid_config = {
        "version": "1.0.0",
        "tenant_id": "test-tenant",
        "default_profile": "profile.python-safety",
    }
    assert list(validator.iter_errors(valid_config)) == []
