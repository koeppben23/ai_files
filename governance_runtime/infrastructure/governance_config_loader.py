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

GOVERNANCE_CONFIG_SCHEMA_ID = "governance-config.v1.schema.json"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _assets_dir() -> Path:
    """Locate the governance assets directory relative to this module."""
    module_root = Path(__file__).parent.parent
    runtime_assets = module_root / "assets"
    if runtime_assets.is_dir():
        return runtime_assets
    legacy_assets = module_root.parent / "governance" / "assets"
    return legacy_assets


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


# ---------------------------------------------------------------------------
# Governance Config Loader (workspace-level)
# ---------------------------------------------------------------------------

def load_governance_config(
    workspace_root: Path,
    *,
    require_valid: bool = True,
) -> dict[str, object]:
    """Load governance configuration from workspace root.

    This function loads the governance-config.json file from the workspace root
    and validates it. If the file is missing, it returns default values.
    If the file is present but invalid, it raises RuntimeError (if require_valid=True).

    Args:
        workspace_root: Path to the workspace root directory.
        require_valid: If True, raise RuntimeError for invalid configs.
                      If False, return defaults on error (including missing file).

    Returns:
        A dict with the validated governance configuration.

    Raises:
        RuntimeError: If require_valid=True and config file is present but invalid.

    Design:
        - File missing → return defaults (backward compatible)
        - File present + valid → use loaded values
        - File present + invalid → fail-closed (require_valid=True) or defaults
        - Unknown keys → fail-closed
    """
    from governance_runtime.domain.default_governance_config import (
        get_default_governance_config,
    )

    config_path = workspace_root / "governance-config.json"

    if not config_path.is_file():
        return get_default_governance_config()

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        if require_valid:
            raise RuntimeError(
                f"governance-config.json unreadable at {config_path}: {exc}"
            ) from exc
        return get_default_governance_config()

    if not isinstance(payload, dict):
        if require_valid:
            raise RuntimeError(
                f"governance-config.json root must be object, got {type(payload).__name__}"
            )
        return get_default_governance_config()

    errors = _validate_governance_config_schema(payload)
    if errors:
        error_msg = f"governance-config.json invalid at {config_path}: {'; '.join(errors)}"
        if require_valid:
            raise RuntimeError(error_msg)
        return get_default_governance_config()

    return payload


def _validate_governance_config_schema(config: dict[str, object]) -> list[str]:
    """Validate governance config against schema requirements.

    Returns a list of error messages (empty = valid).
    Unknown keys cause validation failure to prevent silent misconfiguration.
    """
    errors: list[str] = []

    if "$schema" not in config:
        errors.append("missing required key: $schema")
    elif config["$schema"] != GOVERNANCE_CONFIG_SCHEMA_ID:
        errors.append(f"invalid $schema value: expected '{GOVERNANCE_CONFIG_SCHEMA_ID}', got '{config['$schema']}'")

    for section in ("review", "pipeline", "regulated"):
        if section not in config:
            errors.append(f"missing required section: {section}")
        elif not isinstance(config[section], dict):
            errors.append(f"section '{section}' must be an object")
        else:
            errors.extend(_validate_section(section, config[section]))

    unknown_keys = set(config.keys()) - {"$schema", "review", "pipeline", "regulated"}
    if unknown_keys:
        errors.append(f"unknown top-level keys: {', '.join(sorted(unknown_keys))}")

    return errors


def _validate_section(section: str, section_config: dict) -> list[str]:
    """Validate a single config section."""
    errors: list[str] = []

    if section == "review":
        required = {"phase5_max_review_iterations", "phase6_max_review_iterations"}
        if not required.issubset(section_config.keys()):
            missing = required - section_config.keys()
            errors.append(f"review: missing required keys: {', '.join(sorted(missing))}")
        for key, value in section_config.items():
            if key not in required:
                errors.append(f"review: unknown key '{key}'")
                continue
            if not isinstance(value, int):
                errors.append(f"review.{key} must be integer, got {type(value).__name__}")
            elif value < 1 or value > 100:
                errors.append(f"review.{key} must be between 1 and 100, got {value}")

    elif section == "pipeline":
        required = {"allow_pipeline_mode", "auto_approve_enabled"}
        if not required.issubset(section_config.keys()):
            missing = required - section_config.keys()
            errors.append(f"pipeline: missing required keys: {', '.join(sorted(missing))}")
        for key, value in section_config.items():
            if key not in required:
                errors.append(f"pipeline: unknown key '{key}'")
                continue
            if not isinstance(value, bool):
                errors.append(f"pipeline.{key} must be boolean, got {type(value).__name__}")

    elif section == "regulated":
        required = {"allow_auto_approve", "require_governance_mode_active"}
        if not required.issubset(section_config.keys()):
            missing = required - section_config.keys()
            errors.append(f"regulated: missing required keys: {', '.join(sorted(missing))}")
        for key, value in section_config.items():
            if key not in required:
                errors.append(f"regulated: unknown key '{key}'")
                continue
            if not isinstance(value, bool):
                errors.append(f"regulated.{key} must be boolean, got {type(value).__name__}")

    return errors


def validate_governance_config(config: dict[str, object]) -> list[str]:
    """Public validation function for governance config.

    Returns a list of error messages (empty = valid).
    """
    return _validate_governance_config_schema(config)


def get_review_iterations(
    workspace_root: Path | None = None,
) -> tuple[int, int]:
    """Get phase5 and phase6 review iterations from governance config.

    Args:
        workspace_root: Path to the workspace root directory.
                      If None, returns defaults.

    Returns:
        A tuple of (phase5_max, phase6_max) review iterations.
    """
    if workspace_root is None:
        from governance_runtime.domain.default_governance_config import get_default_review_config
        defaults = get_default_review_config()
        return (defaults["phase5_max_review_iterations"], defaults["phase6_max_review_iterations"])

    config = load_governance_config(workspace_root)
    return (
        config["review"]["phase5_max_review_iterations"],
        config["review"]["phase6_max_review_iterations"],
    )


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
    "load_governance_config",
    "validate_governance_config",
    "get_review_iterations",
    "clear_caches",
]
