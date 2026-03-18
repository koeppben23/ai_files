"""Governance Config Loader — Runtime loading of governance schemas and YAML configs.

Provides functions to locate, load, and cache the governance policy YAML configs
and JSON schemas at runtime. This bridges the gap between the policy files in
governance/assets/ and the domain modules that need them.

Design:
    - Lazy loading with module-level cache (loaded on first access)
    - Pure validation of loaded configs against expected structure
    - Fail-closed: missing or invalid configs raise RuntimeError
    - Zero external dependencies (stdlib + yaml)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _assets_dir() -> Path:
    """Locate the governance/assets directory relative to this module."""
    return Path(__file__).parent.parent / "assets"


def schemas_dir() -> Path:
    """Return the path to governance/assets/schemas/."""
    return _assets_dir() / "schemas"


def config_dir() -> Path:
    """Return the path to governance/assets/config/."""
    return _assets_dir() / "config"


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_schema_cache: dict[str, dict[str, Any]] = {}


def load_schema(name: str) -> dict[str, Any]:
    """Load a JSON schema by filename (e.g. 'audit_contract.v1.schema.json').

    Caches the result after first load. Raises RuntimeError if the file
    does not exist or contains invalid JSON.
    """
    if name in _schema_cache:
        return _schema_cache[name]

    path = schemas_dir() / name
    if not path.is_file():
        raise RuntimeError(f"governance schema not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"governance schema unreadable: {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"governance schema root must be object: {path}")

    _schema_cache[name] = payload
    return payload


def load_all_governance_schemas() -> dict[str, dict[str, Any]]:
    """Load all governance-specific JSON schemas.

    Returns a dict mapping schema filename to parsed content.
    Loads governance control-plane schemas plus externally reviewed
    audit artifact schemas.
    """
    governance_names = [
        "audit_contract.v1.schema.json",
        "failure_report.v1.schema.json",
        "classification.v1.schema.json",
        "access_control.v1.schema.json",
        "retention_policy.v1.schema.json",
        "plan_record.v1.schema.json",
        "repository_manifest.v1.schema.json",
        "run_manifest.v1.schema.json",
        "work_run_snapshot.v2.schema.json",
        "run_checksums.v1.schema.json",
        "ticket_record.v1.schema.json",
        "review_decision_record.v1.schema.json",
        "outcome_record.v1.schema.json",
        "evidence_index.v1.schema.json",
        "finalization_record.v1.schema.json",
        "pr_record.v1.schema.json",
        "provenance_record.v1.schema.json",
        "operating_mode_policy_matrix.v1.schema.json",
        "repo_governance_policy.v1.schema.json",
        "break_glass_record.v1.schema.json",
    ]
    result: dict[str, dict[str, Any]] = {}
    for name in governance_names:
        path = schemas_dir() / name
        if path.is_file():
            result[name] = load_schema(name)
    return result


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------

_config_cache: dict[str, dict[str, Any]] = {}


def load_config(name: str) -> dict[str, Any]:
    """Load a YAML policy config by filename (e.g. 'retention_policy.yaml').

    Caches the result after first load. Raises RuntimeError if the file
    does not exist or contains invalid YAML.
    """
    if name in _config_cache:
        return _config_cache[name]

    path = config_dir() / name
    if not path.is_file():
        raise RuntimeError(f"governance config not found: {path}")

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        raise RuntimeError(f"governance config unreadable: {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"governance config root must be mapping: {path}")

    _config_cache[name] = payload
    return payload


def load_all_governance_configs() -> dict[str, dict[str, Any]]:
    """Load all governance YAML policy configs.

    Returns a dict mapping config filename to parsed content.
    """
    governance_names = [
        "audit_contract.yaml",
        "classification_policy.yaml",
        "access_control_policy.yaml",
        "retention_policy.yaml",
        "operating_mode_policy_matrix.yaml",
    ]
    result: dict[str, dict[str, Any]] = {}
    for name in governance_names:
        path = config_dir() / name
        if path.is_file():
            result[name] = load_config(name)
    return result


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def validate_config_structure(config: Mapping[str, Any], *, required_keys: tuple[str, ...]) -> list[str]:
    """Validate that a loaded config has the expected top-level keys.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    for key in required_keys:
        if key not in config:
            errors.append(f"missing required key: {key}")
    return errors


def validate_policy_metadata(config: Mapping[str, Any]) -> list[str]:
    """Validate the common policy metadata block.

    All governance YAML configs must have a 'policy' block with
    version, contract_version, precedence_level, and pack_locked.
    """
    policy = config.get("policy")
    if not isinstance(policy, dict):
        return ["missing or invalid 'policy' block"]

    errors: list[str] = []
    for field in ("version", "contract_version", "precedence_level", "pack_locked"):
        if field not in policy:
            errors.append(f"policy.{field} missing")
    if "pack_locked" in policy and policy["pack_locked"] is not True:
        errors.append("policy.pack_locked must be true for engine master policy")
    return errors


def validate_audit_contract_config(config: Mapping[str, Any]) -> list[str]:
    """Validate audit_contract.yaml structure."""
    errors = validate_policy_metadata(config)
    errors.extend(validate_config_structure(
        config,
        required_keys=("policy", "run_archive", "lifecycle_rules", "artifact_rules", "consistency_rules", "integrity"),
    ))
    return errors


def validate_classification_config(config: Mapping[str, Any]) -> list[str]:
    """Validate classification_policy.yaml structure."""
    errors = validate_policy_metadata(config)
    errors.extend(validate_config_structure(
        config,
        required_keys=("policy", "classification_levels", "redaction_strategies", "default_classification"),
    ))
    return errors


def validate_access_control_config(config: Mapping[str, Any]) -> list[str]:
    """Validate access_control_policy.yaml structure."""
    errors = validate_policy_metadata(config)
    errors.extend(validate_config_structure(
        config,
        required_keys=("policy", "roles", "actions", "default_policy"),
    ))
    return errors


def validate_retention_config(config: Mapping[str, Any]) -> list[str]:
    """Validate retention_policy.yaml structure."""
    errors = validate_policy_metadata(config)
    errors.extend(validate_config_structure(
        config,
        required_keys=("policy", "retention_periods", "retention_classes", "regulated_mode", "legal_hold", "deletion_guards"),
    ))
    return errors


def validate_operating_mode_policy_matrix_config(config: Mapping[str, Any]) -> list[str]:
    """Validate operating_mode_policy_matrix.yaml structure."""
    errors = validate_policy_metadata(config)
    errors.extend(validate_config_structure(config, required_keys=("policy", "profiles")))
    profiles = config.get("profiles")
    if not isinstance(profiles, dict):
        errors.append("profiles must be mapping")
        return errors
    for profile in ("solo", "team", "regulated"):
        node = profiles.get(profile)
        if not isinstance(node, dict):
            errors.append(f"profiles.{profile} missing")
            continue
        required_fields = (
            "audit_depth",
            "approval_context",
            "evidence_completeness",
            "classification_redaction",
            "retention_restore_hold",
            "verify_failure_semantics",
        )
        for field in required_fields:
            if field not in node:
                errors.append(f"profiles.{profile}.{field} missing")
    return errors


def validate_all_governance_configs() -> dict[str, list[str]]:
    """Load and validate all governance configs.

    Returns a dict mapping config filename to list of validation errors.
    Empty error list = valid.
    """
    validators = {
        "audit_contract.yaml": validate_audit_contract_config,
        "classification_policy.yaml": validate_classification_config,
        "access_control_policy.yaml": validate_access_control_config,
        "retention_policy.yaml": validate_retention_config,
        "operating_mode_policy_matrix.yaml": validate_operating_mode_policy_matrix_config,
    }
    results: dict[str, list[str]] = {}
    for name, validator in validators.items():
        try:
            config = load_config(name)
            results[name] = validator(config)
        except RuntimeError as exc:
            results[name] = [str(exc)]
    return results


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def clear_caches() -> None:
    """Clear all cached schemas and configs (useful for testing)."""
    _schema_cache.clear()
    _config_cache.clear()


__all__ = [
    "schemas_dir",
    "config_dir",
    "load_schema",
    "load_all_governance_schemas",
    "load_config",
    "load_all_governance_configs",
    "validate_config_structure",
    "validate_policy_metadata",
    "validate_audit_contract_config",
    "validate_classification_config",
    "validate_access_control_config",
    "validate_retention_config",
    "validate_operating_mode_policy_matrix_config",
    "validate_all_governance_configs",
    "clear_caches",
]
