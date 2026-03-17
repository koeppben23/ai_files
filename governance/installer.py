"""
Governance Integration for Installer - Wave 13

This module provides the integration layer between the installer and the
governance API. It maps installer-specific collection logic to governance
layer classification.

This enables:
- Using governance API instead of installer heuristics
- Single source of truth for file classification
- Cleaner separation between installer logic and governance rules

IMPORTANT: All classification decisions are derived exclusively from
governance installer/layer APIs. Legacy hardcoded include/exclude lists
were removed intentionally.

Usage:
    from governance.installer import collect_commands, collect_content
    
    # Get canonical commands only
    commands = collect_commands(source_dir)
    
    # Get content files
    content = collect_content(source_dir)

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
from governance.engine.command_surface import is_canonical_command


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


def collect_commands(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect only canonical OpenCode commands.
    
    These are the 8 true slash commands:
    continue.md, plan.md, review.md, review-decision.md, ticket.md,
    implement.md, implementation-decision.md, audit-readout.md
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of canonical command paths
    """
    files = []
    for p in iter_files_recursive(source_dir):
        rel_path = _to_relative(p, source_dir)
        path_str = rel_path.as_posix() if isinstance(rel_path, Path) else str(rel_path)
        basename = path_str.split("/")[-1]
        if is_canonical_command(basename):
            if relative:
                files.append(rel_path)
            else:
                files.append(p)
    return sorted(files)


def collect_opencode_integration(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect all OpenCode integration files.
    
    This includes:
    - Canonical commands (collect_commands)
    - OpenCode plugins (from plugins/ directory)
    - OpenCode config files
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of OpenCode integration paths
    """
    files = []
    for p in iter_files_recursive(source_dir):
        rel_path = _to_relative(p, source_dir)
        path_str = rel_path.as_posix() if isinstance(rel_path, Path) else str(rel_path)
        
        layer = classify_layer(path_str)
        if layer == GovernanceLayer.OPENCODE_INTEGRATION:
            if relative:
                files.append(rel_path)
            else:
                files.append(p)
    return sorted(files)


def collect_content(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect governance content files.
    
    This includes:
    - master.md, rules.md (content, not commands)
    - docs/*.md
    - profiles/**
    - templates/**
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of content paths
    """
    return collect_by_layer(source_dir, GovernanceLayer.GOVERNANCE_CONTENT, relative)


def collect_specs(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect governance spec files.
    
    This includes:
    - phase_api.yaml
    - rules.yml
    - schemas/**
    - governance.paths.json
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of spec paths
    """
    return collect_by_layer(source_dir, GovernanceLayer.GOVERNANCE_SPEC, relative)


def collect_runtime(
    source_dir: Path,
    relative: bool = True,
) -> list[Path]:
    """
    Collect governance runtime files.
    
    This includes:
    - Python code in governance/**
    - Entry points
    
    Args:
        source_dir: Root directory to scan
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of runtime paths
    """
    return collect_by_layer(source_dir, GovernanceLayer.GOVERNANCE_RUNTIME, relative)


def install_commands_target() -> str:
    """Get the target path for commands installation."""
    return "commands"


def install_content_target() -> str:
    """Get the target path for content installation."""
    return "commands"


def install_spec_target() -> str:
    """Get the target path for spec installation."""
    return "commands"


def install_runtime_target() -> str:
    """Get the target path for runtime installation."""
    return "commands/governance"


def collect_for_install_target(
    source_dir: Path,
    target: str,
    relative: bool = True,
) -> list[Path]:
    """
    Collect files for a specific install target.
    
    Target can be one of:
    - "commands": Only canonical commands
    - "content": Governance content (master.md, rules.md, docs, profiles, templates)
    - "specs": Governance specs (phase_api.yaml, rules.yml, schemas)
    - "runtime": Governance runtime (Python code)
    - "opencode_integration": Commands + plugins + config
    
    Args:
        source_dir: Root directory to scan
        target: Install target name
        relative: If True, return paths relative to source_dir
        
    Returns:
        List of paths for the specified target
    """
    if target == "commands":
        return collect_commands(source_dir, relative=relative)
    elif target == "content":
        return collect_content(source_dir, relative=relative)
    elif target == "specs":
        return collect_specs(source_dir, relative=relative)
    elif target == "runtime":
        return collect_runtime(source_dir, relative=relative)
    elif target == "opencode_integration":
        return collect_opencode_integration(source_dir, relative=relative)
    else:
        return []
