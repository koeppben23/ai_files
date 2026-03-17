"""
Governance Integration for Installer - Wave 11

This module provides the integration layer between the installer and the
governance API. It maps installer-specific collection logic to governance
layer classification.

This enables:
- Using governance API instead of installer heuristics
- Single source of truth for file classification
- Cleaner separation between installer logic and governance rules

Usage:
    from governance.installer import collect_by_layer, is_installable_path
    
    # Get all installable files from source_dir
    installable = collect_by_layer(source_dir, GovernanceLayer.GOVERNANCE_CONTENT)
    
    # Check if a single path is installable
    if is_installable_path(some_path):
        print("This file should be installed")

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from governance import (
    GovernanceLayer,
    classify_layer,
    is_installable_layer,
    is_static_content_payload,
)


def _to_relative(path: Path, base: Path) -> Path:
    """Convert absolute path to relative path for classification."""
    try:
        return path.relative_to(base)
    except ValueError:
        return path


def iter_files_recursive(root: Path) -> Iterator[Path]:
    """Iterate all files under root recursively."""
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def collect_by_layer(
    source_dir: Path,
    layer: GovernanceLayer,
    relative: bool = True,
) -> list[Path]:
    """
    Collect all files of a specific layer from source directory.
    
    Args:
        source_dir: Root directory to scan
        layer: Governance layer to filter by
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of paths belonging to the specified layer
    """
    files = []
    for p in iter_files_recursive(source_dir):
        rel_path = _to_relative(p, source_dir)
        if classify_layer(rel_path) == layer:
            if relative:
                files.append(rel_path)
            else:
                files.append(p)
    return sorted(files)


def collect_installable(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect all installable files from source directory.
    
    This uses is_installable_layer() to determine which files
    should be included in the installation.
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of installable file paths
    """
    files = []
    for p in iter_files_recursive(source_dir):
        rel_path = _to_relative(p, source_dir)
        if is_installable_layer(classify_layer(rel_path)):
            if relative:
                files.append(rel_path)
            else:
                files.append(p)
    return sorted(files)


def collect_static_payload(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect all static content payload files.
    
    These are the pure governance content/spec files that can be
    distributed as static files without installation.
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of static payload file paths
    """
    files = []
    for p in iter_files_recursive(source_dir):
        rel_path = _to_relative(p, source_dir)
        if is_static_content_payload(classify_layer(rel_path)):
            if relative:
                files.append(rel_path)
            else:
                files.append(p)
    return sorted(files)


def is_installable_path(path: Path | str, base_dir: Path | None = None) -> bool:
    """
    Check if a path is installable.
    
    Uses full relative path for classification when base_dir is provided,
    otherwise falls back to basename (for backward compatibility).
    
    Args:
        path: Path to check (can be relative or absolute)
        base_dir: Optional base directory for relative path resolution
        
    Returns:
        True if the path should be included in installation
    """
    path_str = _resolve_for_classification(path, base_dir)
    return is_installable_layer(classify_layer(path_str))


def get_layer_info(path: Path | str, base_dir: Path | None = None) -> dict:
    """
    Get detailed layer information for a path.
    
    Uses full relative path for classification when base_dir is provided.
    
    Args:
        path: Path to analyze
        base_dir: Optional base directory for relative path resolution
        
    Returns:
        Dict with layer, is_installable, is_static_payload
    """
    path_str = _resolve_for_classification(path, base_dir)
    layer = classify_layer(path_str)
    return {
        "layer": layer,
        "layer_name": layer.name,
        "is_installable": is_installable_layer(layer),
        "is_static_payload": is_static_content_payload(layer),
    }


def exclude_state_files(paths: list[Path], base_dir: Path | None = None) -> list[Path]:
    """
    Filter out state files from a list of paths.
    
    Uses full relative path for classification when base_dir is provided.
    State files (runtime state, logs) should never be installed.
    
    Args:
        paths: List of paths to filter
        base_dir: Optional base directory for relative path resolution
        
    Returns:
        List of paths excluding state files
    """
    result = []
    for p in paths:
        path_str = _resolve_for_classification(p, base_dir)
        layer = classify_layer(path_str)
        if layer != GovernanceLayer.REPO_RUN_STATE:
            result.append(p)
    return result


def _resolve_for_classification(path: Path | str, base_dir: Path | None) -> str:
    """
    Resolve a path for classification.
    
    If base_dir is provided, returns relative path from base_dir.
    Otherwise returns the path as-is (or basename for Path objects).
    """
    if base_dir is not None and isinstance(path, Path):
        try:
            rel = path.relative_to(base_dir)
            return rel.as_posix()
        except ValueError:
            pass
    
    if isinstance(path, Path):
        return path.as_posix()
    
    return path
