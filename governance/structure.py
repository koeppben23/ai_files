"""
Governance Directory Structure Module - Wave 12 (Revised)

This module provides directory structure utilities as a THIN WRAPPER over
the existing layer classification and contract systems.

IMPORTANT: This is NOT a separate classification truth. It maps physical
directories to governance layers and provides migration helpers.

Target Structure (defined in governance/contract.py via ALLOWED_PREFIXES):
- commands/          → OPENCODE_INTEGRATION
- governance/       → GOVERNANCE_RUNTIME
- docs/             → GOVERNANCE_CONTENT
- schemas/, governance/contracts/ → GOVERNANCE_SPECS
- workspaces/       → REPO_RUN_STATE

This module provides:
- Directory type mapping (as convenience layer over classify_layer)
- Structure summary utilities
- Integration with existing layer/contract systems

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Iterator, Iterable

from governance import (
    GovernanceLayer,
    classify_layer,
    is_static_content_payload,
    is_installable_layer,
    get_allowed_prefixes_for_layer,
)
from governance.contract import ALLOWED_PREFIXES


class DirectoryType(Enum):
    """
    Directory types for governance structure.
    
    This is a convenience mapping to GovernanceLayer, NOT a separate classification.
    """
    COMMAND_SURFACE = auto()       # → OPENCODE_INTEGRATION
    GOVERNANCE_RUNTIME = auto()   # → GOVERNANCE_RUNTIME
    GOVERNANCE_CONTENT = auto()   # → GOVERNANCE_CONTENT
    GOVERNANCE_SPECS = auto()     # → GOVERNANCE_SPECS
    PROFILES = auto()            # → GOVERNANCE_CONTENT
    TEMPLATES = auto()           # → GOVERNANCE_CONTENT
    WORKSPACES = auto()          # → REPO_RUN_STATE
    UNKNOWN = auto()             # → No layer match


def _layer_to_directory_type(layer: GovernanceLayer) -> DirectoryType:
    """Map GovernanceLayer to DirectoryType."""
    mapping = {
        GovernanceLayer.OPENCODE_INTEGRATION: DirectoryType.COMMAND_SURFACE,
        GovernanceLayer.GOVERNANCE_RUNTIME: DirectoryType.GOVERNANCE_RUNTIME,
        GovernanceLayer.GOVERNANCE_CONTENT: DirectoryType.GOVERNANCE_CONTENT,
        GovernanceLayer.GOVERNANCE_SPEC: DirectoryType.GOVERNANCE_SPECS,
        GovernanceLayer.REPO_RUN_STATE: DirectoryType.WORKSPACES,
    }
    return mapping.get(layer, DirectoryType.UNKNOWN)


def get_directory_type(path: str | Path) -> DirectoryType | None:
    """
    Get directory type for a path.
    
    This is a CONVENIENCE WRAPPER around classify_layer().
    For directories (paths ending in /), it uses prefix-based classification.
    For files, it uses classify_layer().
    
    Args:
        path: Path to check
        
    Returns:
        DirectoryType if path has a governance layer, None otherwise
    """
    path_str = str(path)
    
    if not path_str.endswith("/"):
        path_str_for_dir = path_str + "/"
    else:
        path_str_for_dir = path_str
    
    for layer, prefixes in ALLOWED_PREFIXES.items():
        for prefix in prefixes:
            if path_str == prefix or path_str_for_dir == prefix:
                return _layer_to_directory_type(layer)
    
    layer = classify_layer(path)
    if layer == GovernanceLayer.UNKNOWN:
        return None
    return _layer_to_directory_type(layer)


def is_valid_structure(path: str | Path) -> tuple[bool, DirectoryType | None]:
    """
    Check if a path follows valid governance structure.
    
    This is a WRAPPER around classify_layer() - if the layer is known,
    the structure is valid.
    
    Args:
        path: Path to validate
        
    Returns:
        Tuple of (is_valid, directory_type)
    """
    dir_type = get_directory_type(path)
    return (dir_type is not None, dir_type)


def get_legacy_paths() -> tuple[str, ...]:
    """
    Get paths that are legacy and should be migrated.
    
    Currently returns empty - legacy paths need to be defined based on
    actual repository analysis.
    """
    return ()


def get_layer_for_directory_type(dir_type: DirectoryType) -> GovernanceLayer | None:
    """Get GovernanceLayer for a DirectoryType."""
    mapping = {
        DirectoryType.COMMAND_SURFACE: GovernanceLayer.OPENCODE_INTEGRATION,
        DirectoryType.GOVERNANCE_RUNTIME: GovernanceLayer.GOVERNANCE_RUNTIME,
        DirectoryType.GOVERNANCE_CONTENT: GovernanceLayer.GOVERNANCE_CONTENT,
        DirectoryType.GOVERNANCE_SPECS: GovernanceLayer.GOVERNANCE_SPEC,
        DirectoryType.PROFILES: GovernanceLayer.GOVERNANCE_CONTENT,
        DirectoryType.TEMPLATES: GovernanceLayer.GOVERNANCE_CONTENT,
        DirectoryType.WORKSPACES: GovernanceLayer.REPO_RUN_STATE,
    }
    return mapping.get(dir_type)


def get_allowed_directories_for_type(dir_type: DirectoryType) -> tuple[str, ...]:
    """Get allowed directory prefixes for a DirectoryType."""
    layer = get_layer_for_directory_type(dir_type)
    if layer is None:
        return ()
    return get_allowed_prefixes_for_layer(layer)


def validate_structure_against_contract(
    path: str | Path,
    expected_dir_type: DirectoryType,
) -> tuple[bool, str]:
    """
    Validate that a path is in the correct location for its directory type.
    
    This uses the ACTUAL governance contract (from contract.py) to validate,
    not just prefix matching.
    
    Args:
        path: Path to validate
        expected_dir_type: Expected directory type
        
    Returns:
        Tuple of (is_valid, message)
    """
    actual_layer = classify_layer(path)
    expected_layer = get_layer_for_directory_type(expected_dir_type)
    
    if expected_layer is None:
        return False, f"Unknown directory type: {expected_dir_type}"
    
    if actual_layer != expected_layer:
        return False, f"Path {path} has layer {actual_layer.name}, expected {expected_layer.name}"
    
    return True, "Valid"


def get_structure_summary(root: Path) -> dict:
    """
    Get a summary of the directory structure.
    
    Uses classify_layer() for actual classification.
    
    Args:
        root: Root directory to analyze
        
    Returns:
        Dict mapping DirectoryType to file counts
    """
    from collections import defaultdict
    
    summary: dict[DirectoryType, int] = defaultdict(int)
    
    for p in root.rglob("*"):
        if p.is_file():
            dir_type = get_directory_type(p)
            if dir_type is not None:
                summary[dir_type] += 1
    
    return dict(summary)
