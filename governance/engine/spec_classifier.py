"""
Spec Classification Module - Wave 2

Defines what constitutes "governance_spec" - machine-readable SSOT files.

This module provides classification functions to identify spec files
that must be separated from content and runtime.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path


# Spec file patterns - files that are machine-readable SSOT
# This IS the authoritative source of truth for spec classification
# Note: root-level spec files are listed without trailing slash
SPEC_PATTERNS: frozenset = frozenset({
    # Root level spec files
    "phase_api.yaml",
    "rules.yml",
    # Governance spec directories (legacy)
    "schemas",
    "governance/assets/schemas",
    "governance/assets/config",
    "governance/assets/configs",
    "governance/contracts",
    "governance/receipts",
    # Governance spec directories (new Wave 15)
    "governance_spec",
    # Ruleset specs
    "rulesets",
    "rulesets/profiles",
    "rulesets/core",
    # Profile addon manifests
    "profiles/addons",
    # Template catalogs (full path required)
    "templates/github-actions/template_catalog.json",
})


def _matches_spec_pattern(path: Path) -> bool:
    """
    Check if path matches any SPEC_PATTERNS prefix.
    
    This is the AUTHORITATIVE classification method.
    """
    path_str = path.as_posix()
    
    # Check exact file matches
    for pattern in SPEC_PATTERNS:
        if not pattern.endswith(("/", ".yaml", ".yml", ".json")):
            # This is a directory pattern
            if path_str == pattern:
                return True
        else:
            # This is a file pattern
            if path_str == pattern:
                return True
    
    return False


def is_spec_file(path: Path) -> bool:
    """
    Determine if a file is a governance spec (machine-readable SSOT).
    
    Classification rules (in priority order):
    1. Exact match in SPEC_PATTERNS (authoritative)
    2. File in a directory that matches SPEC_PATTERNS prefix
    
    This method is PRECISE - it does NOT classify broadly based on
    directory names alone. Each spec location must be explicitly
    defined in SPEC_PATTERNS.
    """
    path = Path(path.as_posix() if hasattr(path, 'as_posix') else str(path))
    
    # Check authoritative SPEC_PATTERNS (file patterns)
    path_str = path.as_posix()
    if path_str in SPEC_PATTERNS:
        return True
    
    # Check if file is in a spec directory
    for parent in path.parents:
        parent_str = parent.as_posix()
        if parent_str in SPEC_PATTERNS:
            return True
    
    return False


def is_spec_directory(path: Path) -> bool:
    """
    Determine if a directory is a spec directory.
    
    A directory is spec ONLY if it exactly matches a SPEC_PATTERNS entry.
    (No broad child-matching - each spec location must be explicit.)
    """
    path = Path(path.as_posix() if hasattr(path, 'as_posix') else str(path))
    path_str = path.as_posix()
    
    # Exact match only
    return path_str in SPEC_PATTERNS


def get_spec_paths(repo_root: Path) -> list[Path]:
    """
    Get all spec paths under a repository root.
    
    This is a CURATED scanner - it only searches known spec locations
    defined in SPEC_PATTERNS.
    """
    spec_paths = []
    
    # Scan each spec directory from SPEC_PATTERNS
    for pattern in SPEC_PATTERNS:
        if pattern.endswith((".yaml", ".yml", ".json")):
            # Root-level spec file
            spec_path = repo_root / pattern
            if spec_path.exists():
                spec_paths.append(spec_path)
        else:
            # Spec directory
            spec_dir = repo_root / pattern
            if spec_dir.exists() and spec_dir.is_dir():
                for item in spec_dir.rglob("*"):
                    if item.is_file() and is_spec_file(item):
                        spec_paths.append(item)
    
    return sorted(spec_paths)


# Classification constants for testing
GOVERNANCE_SPEC_PATTERNS = {
    "phase_api.yaml",
    "rules.yml", 
    "schemas/",
    "governance/assets/schemas/",
    "governance/assets/config/",
    "governance/contracts/",
    "governance/receipts/",
    "rulesets/",
    "profiles/addons/",
    "templates/**/template_catalog.json",
}
