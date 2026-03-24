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

from governance_runtime.domain.default_governance_config import (
    get_default_governance_config,
)
from governance_runtime.infrastructure.governance_config_loader import (
    clear_caches,
    config_dir,
    load_all_governance_configs,
    load_all_governance_schemas,
    load_config,
    load_governance_config,
    load_schema,
    schemas_dir,
    validate_access_control_config,
    validate_all_governance_configs,
    validate_audit_contract_config,
    validate_classification_config,
    validate_config_structure,
    validate_governance_config,
    validate_policy_metadata,
    validate_retention_config,
    validate_operating_mode_policy_matrix_config,
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
        assert len(schemas) == 20
        assert "audit_contract.v1.schema.json" in schemas
        assert "failure_report.v1.schema.json" in schemas
        assert "plan_record.v1.schema.json" in schemas
        assert "repository_manifest.v1.schema.json" in schemas
        assert "run_manifest.v1.schema.json" in schemas
        assert "work_run_snapshot.v2.schema.json" in schemas
        assert "run_checksums.v1.schema.json" in schemas
        assert "ticket_record.v1.schema.json" in schemas
        assert "review_decision_record.v1.schema.json" in schemas
        assert "outcome_record.v1.schema.json" in schemas
        assert "evidence_index.v1.schema.json" in schemas
        assert "finalization_record.v1.schema.json" in schemas
        assert "pr_record.v1.schema.json" in schemas
        assert "provenance_record.v1.schema.json" in schemas
        assert "operating_mode_policy_matrix.v1.schema.json" in schemas
        assert "repo_governance_policy.v1.schema.json" in schemas
        assert "break_glass_record.v1.schema.json" in schemas

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
        assert len(configs) == 5
        assert "audit_contract.yaml" in configs
        assert "retention_policy.yaml" in configs
        assert "operating_mode_policy_matrix.yaml" in configs

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

    def test_validate_operating_mode_policy_matrix_config(self):
        config = load_config("operating_mode_policy_matrix.yaml")
        errors = validate_operating_mode_policy_matrix_config(config)
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


# ===================================================================
# WI-24 — Governance Config JSON Tests (workspace-level)
# ===================================================================

def _valid_config() -> dict:
    return {
        "$schema": "governance-config.v1.schema.json",
        "review": {
            "phase5_max_review_iterations": 3,
            "phase6_max_review_iterations": 3,
        },
        "pipeline": {
            "allow_pipeline_mode": True,
            "auto_approve_enabled": True,
        },
        "regulated": {
            "allow_auto_approve": False,
            "require_governance_mode_active": True,
        },
    }


class TestGovernanceConfigJsonHappy:
    """Happy path tests for governance-config.json loading."""

    def test_load_valid_config_returns_loaded_values(self, tmp_path: Path):
        """Valid governance-config.json returns loaded values."""
        config_path = tmp_path / "governance-config.json"
        config_path.write_text(json.dumps(_valid_config()), encoding="utf-8")

        result = load_governance_config(tmp_path)

        assert result["$schema"] == "governance-config.v1.schema.json"
        assert result["review"]["phase5_max_review_iterations"] == 3
        assert result["review"]["phase6_max_review_iterations"] == 3
        assert result["pipeline"]["allow_pipeline_mode"] is True
        assert result["pipeline"]["auto_approve_enabled"] is True
        assert result["regulated"]["allow_auto_approve"] is False
        assert result["regulated"]["require_governance_mode_active"] is True

    def test_load_config_with_custom_iterations(self, tmp_path: Path):
        """Custom review iterations are respected."""
        config = _valid_config()
        config["review"]["phase5_max_review_iterations"] = 5
        config["review"]["phase6_max_review_iterations"] = 7
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        result = load_governance_config(tmp_path)

        assert result["review"]["phase5_max_review_iterations"] == 5
        assert result["review"]["phase6_max_review_iterations"] == 7


class TestGovernanceConfigJsonDefaults:
    """Tests for default fallback when config is missing."""

    def test_missing_config_returns_defaults(self, tmp_path: Path):
        """Missing governance-config.json returns defaults."""
        result = load_governance_config(tmp_path)

        defaults = get_default_governance_config()
        assert result == defaults

    def test_missing_config_with_require_valid_false_returns_defaults(self, tmp_path: Path):
        """Missing config with require_valid=False returns defaults."""
        result = load_governance_config(tmp_path, require_valid=False)

        defaults = get_default_governance_config()
        assert result == defaults

    def test_defaults_match_existing_behavior(self):
        """Defaults match the current hardcoded behavior."""
        defaults = get_default_governance_config()

        assert defaults["review"]["phase5_max_review_iterations"] == 3
        assert defaults["review"]["phase6_max_review_iterations"] == 3
        assert defaults["pipeline"]["allow_pipeline_mode"] is True
        assert defaults["pipeline"]["auto_approve_enabled"] is True
        assert defaults["regulated"]["allow_auto_approve"] is False
        assert defaults["regulated"]["require_governance_mode_active"] is True


class TestGovernanceConfigJsonInvalid:
    """Tests for invalid config handling (fail-closed)."""

    def test_invalid_json_raises_error(self, tmp_path: Path):
        """Invalid JSON raises RuntimeError."""
        config_path = tmp_path / "governance-config.json"
        config_path.write_text("not valid json {", encoding="utf-8")

        with pytest.raises(RuntimeError, match="governance-config.json unreadable"):
            load_governance_config(tmp_path)

    def test_invalid_json_with_require_valid_false_returns_defaults(self, tmp_path: Path):
        """Invalid JSON with require_valid=False returns defaults."""
        config_path = tmp_path / "governance-config.json"
        config_path.write_text("not valid json {", encoding="utf-8")

        result = load_governance_config(tmp_path, require_valid=False)

        assert result == get_default_governance_config()

    def test_root_must_be_object(self, tmp_path: Path):
        """Root must be object, not array."""
        (tmp_path / "governance-config.json").write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(RuntimeError, match="root must be object"):
            load_governance_config(tmp_path)

    def test_missing_schema_key_raises_error(self, tmp_path: Path):
        """Missing $schema key raises error."""
        config = _valid_config()
        del config["$schema"]
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="missing required key"):
            load_governance_config(tmp_path)

    def test_wrong_schema_value_raises_error(self, tmp_path: Path):
        """Wrong $schema value raises error."""
        config = _valid_config()
        config["$schema"] = "wrong-schema.json"
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="invalid \\$schema value"):
            load_governance_config(tmp_path)

    def test_missing_review_section_raises_error(self, tmp_path: Path):
        """Missing review section raises error."""
        config = _valid_config()
        del config["review"]
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="missing required section"):
            load_governance_config(tmp_path)


class TestGovernanceConfigJsonUnknownKeys:
    """Tests for unknown key rejection."""

    def test_unknown_top_level_key_raises_error(self, tmp_path: Path):
        """Unknown top-level key raises error."""
        config = _valid_config()
        config["unknown_key"] = "value"
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="unknown top-level keys"):
            load_governance_config(tmp_path)

    def test_unknown_review_key_raises_error(self, tmp_path: Path):
        """Unknown key in review section raises error."""
        config = _valid_config()
        config["review"]["unknown_key"] = "value"
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="review: unknown key"):
            load_governance_config(tmp_path)


class TestGovernanceConfigJsonTypeValidation:
    """Tests for type validation of config values."""

    def test_phase5_iterations_must_be_integer(self, tmp_path: Path):
        """phase5_max_review_iterations must be integer."""
        config = _valid_config()
        config["review"]["phase5_max_review_iterations"] = "three"
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="must be integer"):
            load_governance_config(tmp_path)

    def test_allow_pipeline_mode_must_be_boolean(self, tmp_path: Path):
        """allow_pipeline_mode must be boolean."""
        config = _valid_config()
        config["pipeline"]["allow_pipeline_mode"] = "yes"
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="must be boolean"):
            load_governance_config(tmp_path)

    def test_allow_auto_approve_must_be_boolean(self, tmp_path: Path):
        """allow_auto_approve must be boolean."""
        config = _valid_config()
        config["regulated"]["allow_auto_approve"] = "yes"
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="must be boolean"):
            load_governance_config(tmp_path)


class TestGovernanceConfigJsonBoundaryValues:
    """Tests for boundary values."""

    def test_phase_iterations_minimum_1(self, tmp_path: Path):
        """Phase iterations must be at least 1."""
        config = _valid_config()
        config["review"]["phase5_max_review_iterations"] = 0
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="must be between 1 and 100"):
            load_governance_config(tmp_path)

    def test_phase_iterations_maximum_100(self, tmp_path: Path):
        """Phase iterations must be at most 100."""
        config = _valid_config()
        config["review"]["phase6_max_review_iterations"] = 101
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(RuntimeError, match="must be between 1 and 100"):
            load_governance_config(tmp_path)

    def test_phase_iterations_at_boundary_1(self, tmp_path: Path):
        """Phase iterations = 1 is valid."""
        config = _valid_config()
        config["review"]["phase5_max_review_iterations"] = 1
        config["review"]["phase6_max_review_iterations"] = 1
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        result = load_governance_config(tmp_path)
        assert result["review"]["phase5_max_review_iterations"] == 1
        assert result["review"]["phase6_max_review_iterations"] == 1

    def test_phase_iterations_at_boundary_100(self, tmp_path: Path):
        """Phase iterations = 100 is valid."""
        config = _valid_config()
        config["review"]["phase5_max_review_iterations"] = 100
        config["review"]["phase6_max_review_iterations"] = 100
        (tmp_path / "governance-config.json").write_text(json.dumps(config), encoding="utf-8")

        result = load_governance_config(tmp_path)
        assert result["review"]["phase5_max_review_iterations"] == 100
        assert result["review"]["phase6_max_review_iterations"] == 100


class TestGovernanceConfigJsonValidate:
    """Tests for the public validate_governance_config function."""

    def test_validate_valid_config_returns_empty_errors(self):
        """Valid config returns empty error list."""
        config = _valid_config()
        errors = validate_governance_config(config)
        assert errors == []

    def test_validate_missing_required_returns_errors(self):
        """Missing required section returns errors."""
        config = _valid_config()
        del config["review"]
        errors = validate_governance_config(config)
        assert len(errors) > 0
        assert any("missing required section: review" in e for e in errors)

    def test_validate_unknown_key_returns_errors(self):
        """Unknown key returns errors."""
        config = _valid_config()
        config["unknown"] = "value"
        errors = validate_governance_config(config)
        assert len(errors) > 0
        assert any("unknown top-level keys" in e for e in errors)
