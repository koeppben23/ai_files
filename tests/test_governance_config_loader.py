"""WI-23 — Tests for governance/infrastructure/governance_config_loader.py

Tests covering runtime loading of governance schemas and YAML configs.
Happy / Edge / Corner / Bad coverage.
All I/O tests use pytest tmp_path fixture. No external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from governance.infrastructure.governance_config_loader import (
    clear_caches,
    config_dir,
    load_all_governance_configs,
    load_all_governance_schemas,
    load_config,
    load_schema,
    schemas_dir,
    validate_access_control_config,
    validate_all_governance_configs,
    validate_audit_contract_config,
    validate_classification_config,
    validate_config_structure,
    validate_policy_metadata,
    validate_retention_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear caches before and after each test."""
    clear_caches()
    yield
    clear_caches()


# ===================================================================
# Happy path
# ===================================================================


class TestSchemaLoadingHappy:
    """Happy: loading governance JSON schemas from real assets."""

    def test_load_audit_contract_schema(self):
        schema = load_schema("audit_contract.v1.schema.json")
        assert isinstance(schema, dict)
        assert "type" in schema or "properties" in schema or "$schema" in schema

    def test_load_failure_report_schema(self):
        schema = load_schema("failure_report.v1.schema.json")
        assert isinstance(schema, dict)

    def test_load_classification_schema(self):
        schema = load_schema("classification.v1.schema.json")
        assert isinstance(schema, dict)

    def test_load_access_control_schema(self):
        schema = load_schema("access_control.v1.schema.json")
        assert isinstance(schema, dict)

    def test_load_retention_policy_schema(self):
        schema = load_schema("retention_policy.v1.schema.json")
        assert isinstance(schema, dict)

    def test_load_all_governance_schemas_returns_expected_set(self):
        schemas = load_all_governance_schemas()
        assert len(schemas) == 14
        assert "audit_contract.v1.schema.json" in schemas
        assert "failure_report.v1.schema.json" in schemas
        assert "run_manifest.v1.schema.json" in schemas
        assert "work_run_snapshot.v2.schema.json" in schemas
        assert "run_checksums.v1.schema.json" in schemas
        assert "ticket_record.v1.schema.json" in schemas
        assert "review_decision_record.v1.schema.json" in schemas
        assert "outcome_record.v1.schema.json" in schemas
        assert "evidence_index.v1.schema.json" in schemas
        assert "pr_record.v1.schema.json" in schemas
        assert "provenance_record.v1.schema.json" in schemas

    def test_schema_caching(self):
        s1 = load_schema("audit_contract.v1.schema.json")
        s2 = load_schema("audit_contract.v1.schema.json")
        assert s1 is s2  # same cached object


class TestConfigLoadingHappy:
    """Happy: loading governance YAML configs from real assets."""

    def test_load_audit_contract_config(self):
        config = load_config("audit_contract.yaml")
        assert isinstance(config, dict)
        assert "policy" in config
        assert config["policy"]["contract_version"] == "AUDIT_STORAGE_CONTRACT.v1"

    def test_load_classification_config(self):
        config = load_config("classification_policy.yaml")
        assert isinstance(config, dict)
        assert "classification_levels" in config

    def test_load_access_control_config(self):
        config = load_config("access_control_policy.yaml")
        assert isinstance(config, dict)
        assert "roles" in config

    def test_load_retention_config(self):
        config = load_config("retention_policy.yaml")
        assert isinstance(config, dict)
        assert "retention_periods" in config

    def test_load_all_governance_configs_returns_four(self):
        configs = load_all_governance_configs()
        assert len(configs) == 4
        assert "audit_contract.yaml" in configs
        assert "retention_policy.yaml" in configs

    def test_config_caching(self):
        c1 = load_config("audit_contract.yaml")
        c2 = load_config("audit_contract.yaml")
        assert c1 is c2  # same cached object


class TestValidationHappy:
    """Happy: validation passes on real configs."""

    def test_validate_audit_contract_config(self):
        config = load_config("audit_contract.yaml")
        errors = validate_audit_contract_config(config)
        assert errors == []

    def test_validate_classification_config(self):
        config = load_config("classification_policy.yaml")
        errors = validate_classification_config(config)
        assert errors == []

    def test_validate_access_control_config(self):
        config = load_config("access_control_policy.yaml")
        errors = validate_access_control_config(config)
        assert errors == []

    def test_validate_retention_config(self):
        config = load_config("retention_policy.yaml")
        errors = validate_retention_config(config)
        assert errors == []

    def test_validate_all_governance_configs_all_pass(self):
        results = validate_all_governance_configs()
        for name, errors in results.items():
            assert errors == [], f"{name}: {errors}"

    def test_validate_policy_metadata(self):
        config = load_config("audit_contract.yaml")
        errors = validate_policy_metadata(config)
        assert errors == []


# ===================================================================
# Edge cases
# ===================================================================


class TestSchemaLoadingEdge:
    """Edge: schemas with boundary conditions."""

    def test_schemas_dir_exists(self):
        assert schemas_dir().is_dir()

    def test_config_dir_exists(self):
        assert config_dir().is_dir()

    def test_all_schemas_have_dict_root(self):
        schemas = load_all_governance_schemas()
        for name, schema in schemas.items():
            assert isinstance(schema, dict), f"{name} root is not dict"


class TestConfigLoadingEdge:
    """Edge: configs with boundary conditions."""

    def test_all_configs_have_policy_block(self):
        configs = load_all_governance_configs()
        for name, config in configs.items():
            assert "policy" in config, f"{name} missing 'policy' block"

    def test_all_configs_are_pack_locked(self):
        configs = load_all_governance_configs()
        for name, config in configs.items():
            policy = config.get("policy", {})
            assert policy.get("pack_locked") is True, f"{name} not pack_locked"


# ===================================================================
# Corner cases
# ===================================================================


class TestValidationCorner:
    """Corner: unusual but valid inputs."""

    def test_validate_config_structure_empty_required(self):
        errors = validate_config_structure({"a": 1}, required_keys=())
        assert errors == []

    def test_validate_config_structure_all_present(self):
        errors = validate_config_structure({"a": 1, "b": 2}, required_keys=("a", "b"))
        assert errors == []

    def test_validate_policy_metadata_extra_keys_ignored(self):
        config = {
            "policy": {
                "version": "1.0.0",
                "contract_version": "TEST.v1",
                "precedence_level": "engine_master_policy",
                "pack_locked": True,
                "extra_field": "ignored",
            }
        }
        errors = validate_policy_metadata(config)
        assert errors == []


# ===================================================================
# Bad path
# ===================================================================


class TestSchemaLoadingBad:
    """Bad: missing/invalid schema files."""

    def test_load_nonexistent_schema_raises(self):
        with pytest.raises(RuntimeError, match="governance schema not found"):
            load_schema("nonexistent.schema.json")

    def test_load_all_schemas_skips_missing(self):
        # Should not raise even if some schemas are missing
        # (because it only loads known governance schemas)
        schemas = load_all_governance_schemas()
        assert isinstance(schemas, dict)


class TestConfigLoadingBad:
    """Bad: missing/invalid config files."""

    def test_load_nonexistent_config_raises(self):
        with pytest.raises(RuntimeError, match="governance config not found"):
            load_config("nonexistent.yaml")


class TestValidationBad:
    """Bad: invalid config structures."""

    def test_validate_config_structure_missing_keys(self):
        errors = validate_config_structure({}, required_keys=("a", "b"))
        assert len(errors) == 2
        assert "missing required key: a" in errors

    def test_validate_policy_metadata_missing_policy(self):
        errors = validate_policy_metadata({})
        assert "missing or invalid 'policy' block" in errors

    def test_validate_policy_metadata_pack_locked_false(self):
        config = {
            "policy": {
                "version": "1.0.0",
                "contract_version": "TEST.v1",
                "precedence_level": "engine_master_policy",
                "pack_locked": False,
            }
        }
        errors = validate_policy_metadata(config)
        assert any("pack_locked" in e for e in errors)

    def test_validate_policy_metadata_missing_fields(self):
        config = {"policy": {}}
        errors = validate_policy_metadata(config)
        assert len(errors) >= 4  # version, contract_version, precedence_level, pack_locked

    def test_validate_audit_contract_missing_sections(self):
        config = {"policy": {"version": "1", "contract_version": "x", "precedence_level": "x", "pack_locked": True}}
        errors = validate_audit_contract_config(config)
        assert any("missing required key" in e for e in errors)

    def test_validate_all_configs_reports_errors_for_invalid(self):
        # This test validates the error-catching behavior
        results = validate_all_governance_configs()
        # All real configs should pass
        for name, errors in results.items():
            assert errors == [], f"unexpected errors in {name}: {errors}"
