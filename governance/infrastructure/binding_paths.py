"""Canonical binding paths loader - SSOT for governance and runtime.

This module provides a single, consistent way to load binding paths
across both governance scripts and runtime components.

All binding path loading MUST go through this module to prevent:
- SSOT leaks where governance interpret bindings differently from runtime
- Path drift where files are written to wrong locations
- Missing validation of commandsHome/workspacesHome under configRoot
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governance.infrastructure.path_contract import normalize_absolute_path

SUPPORTED_BINDING_SCHEMAS = ("opencode-governance.paths.v1", "governance.paths.v1")


class BindingLoadError(Exception):
    """Raised when binding paths cannot be loaded or validated."""
    pass


def load_binding_paths_strict(
    paths_file: Path,
    *,
    expected_config_root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate binding paths from a governance.paths.json file.
    
    This is the SSOT function for loading binding paths. Both governance
    and runtime MUST use this function to ensure consistent validation.
    
    Args:
        paths_file: Path to governance.paths.json file.
        expected_config_root: Optional expected config root for additional validation.
    
    Returns:
        Tuple of (config_root, paths_dict) where paths_dict contains:
            - commandsHome: Path to commands directory
            - workspacesHome: Path to workspaces directory
            - pythonCommand: Python command string
            - configRoot: Config root path
    
    Raises:
        BindingLoadError: If file is missing, invalid, or paths don't match constraints.
    """
    if not paths_file.is_file():
        raise BindingLoadError(f"Binding file not found: {paths_file}")
    
    try:
        payload = json.loads(paths_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BindingLoadError(f"Invalid JSON in binding file: {e}")
    
    if not isinstance(payload, dict):
        raise BindingLoadError("Binding payload must be a JSON object")
    
    schema = payload.get("schema")
    if schema not in SUPPORTED_BINDING_SCHEMAS:
        raise BindingLoadError(
            f"Unsupported binding schema: {schema}. "
            f"Expected one of: {SUPPORTED_BINDING_SCHEMAS}"
        )
    
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise BindingLoadError("Binding payload missing 'paths' object")
    
    raw_config_root = paths.get("configRoot")
    if not isinstance(raw_config_root, str) or not raw_config_root.strip():
        raise BindingLoadError("paths.configRoot is missing or empty")
    
    try:
        config_root = normalize_absolute_path(raw_config_root, purpose="paths.configRoot")
    except Exception as e:
        raise BindingLoadError(f"Invalid paths.configRoot: {e}")
    
    if expected_config_root is not None:
        expected = normalize_absolute_path(str(expected_config_root), purpose="expected_config_root")
        if config_root != expected:
            raise BindingLoadError(
                f"Config root mismatch: got {config_root}, expected {expected}"
            )
    
    raw_commands = paths.get("commandsHome")
    if not isinstance(raw_commands, str) or not raw_commands.strip():
        raise BindingLoadError("paths.commandsHome is missing or empty")
    
    raw_workspaces = paths.get("workspacesHome")
    if not isinstance(raw_workspaces, str) or not raw_workspaces.strip():
        raise BindingLoadError("paths.workspacesHome is missing or empty")
    
    try:
        commands_home = normalize_absolute_path(raw_commands, purpose="paths.commandsHome")
    except Exception as e:
        raise BindingLoadError(f"Invalid paths.commandsHome: {e}")
    
    try:
        workspaces_home = normalize_absolute_path(raw_workspaces, purpose="paths.workspacesHome")
    except Exception as e:
        raise BindingLoadError(f"Invalid paths.workspacesHome: {e}")
    
    if commands_home != config_root / "commands":
        raise BindingLoadError(
            f"commandsHome must be configRoot/commands: "
            f"got {commands_home}, expected {config_root / 'commands'}"
        )
    
    if workspaces_home != config_root / "workspaces":
        raise BindingLoadError(
            f"workspacesHome must be configRoot/workspaces: "
            f"got {workspaces_home}, expected {config_root / 'workspaces'}"
        )
    
    raw_python = paths.get("pythonCommand")
    python_command = str(raw_python).strip() if isinstance(raw_python, str) else ""
    
    result: dict[str, Any] = {
        "commandsHome": commands_home,
        "workspacesHome": workspaces_home,
        "configRoot": config_root,
        "pythonCommand": python_command,
    }
    
    if "commandProfiles" in payload:
        profiles = payload["commandProfiles"]
        if isinstance(profiles, dict):
            result["commandProfiles"] = {
                str(k).strip(): str(v).strip()
                for k, v in profiles.items()
                if isinstance(k, str) and isinstance(v, str)
            }
    
    return config_root, result
