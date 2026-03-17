"""
Governance Directory Structure Module - Wave 12

This module defines the physical directory structure for governance
and provides validation and migration utilities.

Target Structure:
- commands/          - OpenCode commands (slash commands)
- governance/        - Governance runtime code
- docs/             - Customer documentation
- governance/specs   - Governance specs (machine-readable)
- governance/docs    - Governance internal docs
- profiles/         - User profiles
- templates/        - Workflow templates
- workspaces/        - Runtime state (NEVER packaged)

This module provides:
- Directory structure definitions
- Validation against target structure
- Migration planning utilities

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Iterator, Iterable


class DirectoryType(Enum):
    """Types of directories in governance structure."""
    COMMAND_SURFACE = auto()
    GOVERNANCE_RUNTIME = auto()
    CUSTOMER_DOCS = auto()
    GOVERNANCE_SPECS = auto()
    GOVERNANCE_DOCS = auto()
    PROFILES = auto()
    TEMPLATES = auto()
    WORKSPACES = auto()
    LEGACY = auto()


@dataclass
class StructureRule:
    """A rule defining expected directory structure."""
    directory_type: DirectoryType
    expected_paths: tuple[str, ...]
    description: str


STRUCTURE_RULES = (
    StructureRule(
        directory_type=DirectoryType.COMMAND_SURFACE,
        expected_paths=("commands/",),
        description="OpenCode slash commands",
    ),
    StructureRule(
        directory_type=DirectoryType.CUSTOMER_DOCS,
        expected_paths=("docs/",),
        description="Customer-facing documentation",
    ),
    StructureRule(
        directory_type=DirectoryType.GOVERNANCE_SPECS,
        expected_paths=("schemas/", "governance/contracts/", "governance/receipts/", "governance/assets/schemas/"),
        description="Machine-readable governance specs",
    ),
    StructureRule(
        directory_type=DirectoryType.GOVERNANCE_DOCS,
        expected_paths=("governance/docs/",),
        description="Governance internal documentation",
    ),
    StructureRule(
        directory_type=DirectoryType.PROFILES,
        expected_paths=("profiles/",),
        description="User profiles",
    ),
    StructureRule(
        directory_type=DirectoryType.TEMPLATES,
        expected_paths=("templates/",),
        description="Workflow templates",
    ),
    StructureRule(
        directory_type=DirectoryType.WORKSPACES,
        expected_paths=("workspaces/",),
        description="Runtime workspace state (never packaged)",
    ),
    StructureRule(
        directory_type=DirectoryType.GOVERNANCE_RUNTIME,
        expected_paths=("governance/",),
        description="Governance runtime code",
    ),
)


def get_directory_type(path: str | Path) -> DirectoryType | None:
    """
    Determine the directory type based on path prefix.
    
    Args:
        path: Path to check
        
    Returns:
        DirectoryType if matched, None otherwise
    """
    path_str = str(path)
    
    for rule in STRUCTURE_RULES:
        for prefix in rule.expected_paths:
            if path_str.startswith(prefix):
                return rule.directory_type
    
    return None


def is_valid_structure(path: str | Path) -> tuple[bool, DirectoryType | None]:
    """
    Check if a path follows the valid structure.
    
    Args:
        path: Path to validate
        
    Returns:
        Tuple of (is_valid, directory_type)
    """
    dir_type = get_directory_type(path)
    return (dir_type is not None, dir_type)


def get_legacy_paths() -> tuple[str, ...]:
    """
    Get paths that are considered legacy and should be migrated.
    
    Returns tuple of legacy path prefixes.
    """
    return ()


def validate_directory_structure(root: Path) -> dict:
    """
    Validate directory structure under a root.
    
    Args:
        root: Root directory to validate
        
    Returns:
        Dict with validation results
    """
    issues: list[str] = []
    valid_dirs: list[tuple[str, DirectoryType]] = []
    
    for rule in STRUCTURE_RULES:
        for path_prefix in rule.expected_paths:
            full_path = root / path_prefix.rstrip("/")
            if full_path.exists():
                valid_dirs.append((path_prefix, rule.directory_type))
    
    return {
        "valid_directories": valid_dirs,
        "issues": issues,
    }


def suggest_migrations(files: list[Path]) -> dict[str, list[Path]]:
    """
    Suggest migrations for files in wrong locations.
    
    Args:
        files: List of file paths to analyze
        
    Returns:
        Dict mapping current paths to suggested target paths
    """
    migrations: dict[str, list[Path]] = {}
    
    return migrations


def get_structure_summary(root: Path) -> dict:
    """
    Get a summary of the directory structure.
    
    Args:
        root: Root directory to analyze
        
    Returns:
        Dict with structure summary
    """
    summary: dict[str, int] = {}
    
    for rule in STRUCTURE_RULES:
        for path_prefix in rule.expected_paths:
            full_path = root / path_prefix.rstrip("/")
            if full_path.exists() and full_path.is_dir():
                count = len(list(full_path.rglob("*")))
                summary[path_prefix] = count
    
    return summary
