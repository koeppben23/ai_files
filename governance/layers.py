"""
Governance Layer Integration Module - Wave 7

This module provides the consolidated API for governance layer operations.
It ties together all classification modules and provides validation rules.

Layers:
- opencode_integration: Only TRUE slash commands (not content references)
- governance_runtime: Python code (executable logic)
- governance_content: Human-readable docs, profiles, templates
- governance_spec: Machine-readable SSOT (specs, schemas, contracts)
- repo_run_state: Runtime state and logs (per-repo, never packaged)

Usage:
    from governance.layers import classify_layer, GovernanceLayer
    
    layer = classify_layer("commands/continue.md")
    if layer == GovernanceLayer.OPENCODE_INTEGRATION:
        print("This is a command!")

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Iterable

from governance.engine.layer_classifier import (
    GovernanceLayer,
    classify_layer as _classify_layer,
    get_layer_name,
    is_static_content_payload,
    is_installable_layer,
)

from governance.engine import spec_classifier
from governance.engine import content_classifier
from governance.engine import command_surface
from governance.engine import state_classifier

__all__ = [
    "GovernanceLayer",
    "classify_layer",
    "get_layer_name",
    "is_static_content_payload",
    "is_installable_layer",
    "is_state_file",
    "is_log_file",
    "is_command",
    "is_spec_file",
    "is_content_file",
    "is_runtime_file",
    "get_layer_for_path",
    "iter_files_by_layer",
    "validate_layer_assignment",
    "LayerViolation",
    "get_layer_stats",
]


def classify_layer(path: Path | str) -> GovernanceLayer:
    """
    Classify a path into its governance layer.
    
    This is the main entry point for layer classification.
    """
    return _classify_layer(path)


def is_state_file(path: Path | str) -> bool:
    """Check if a path is a state file."""
    name = Path(path).name if isinstance(path, (Path, str)) else path
    return state_classifier.is_state_file(name)


def is_log_file(path: Path | str) -> bool:
    """Check if a path is a log file."""
    name = Path(path).name if isinstance(path, (Path, str)) else path
    return state_classifier.is_log_file(name)


def is_command(path: Path | str) -> bool:
    """Check if a path is a canonical command."""
    name = Path(path).name if isinstance(path, (Path, str)) else path
    return command_surface.is_canonical_command(name)


def is_spec_file(path: Path | str) -> bool:
    """Check if a path is a spec file."""
    path_obj = Path(path) if isinstance(path, str) else path
    return spec_classifier.is_spec_file(path_obj)


def is_content_file(path: Path | str) -> bool:
    """Check if a path is a content file."""
    path_obj = Path(path) if isinstance(path, str) else path
    return content_classifier.is_content_file(path_obj)


def is_runtime_file(path: Path | str) -> bool:
    """Check if a path is a runtime file."""
    path_obj = Path(path) if isinstance(path, str) else path
    return content_classifier.is_runtime_file(path_obj)


def get_layer_for_path(path: Path | str) -> dict:
    """
    Get detailed layer information for a path.
    
    Returns a dict with:
    - layer: GovernanceLayer enum
    - name: human-readable layer name
    - is_installable: whether the layer can be installed
    - is_static_payload: whether the layer is part of static content
    """
    layer = classify_layer(path)
    return {
        "layer": layer,
        "name": get_layer_name(layer),
        "is_installable": is_installable_layer(layer),
        "is_static_payload": is_static_content_payload(layer),
    }


def iter_files_by_layer(
    paths: Iterable[Path],
    layer: GovernanceLayer
) -> Iterator[Path]:
    """
    Filter paths to only those matching a specific layer.
    
    Args:
        paths: An iterable of paths to filter
        layer: The target governance layer
        
    Yields:
        Paths that belong to the specified layer
        
    Usage:
        for py_file in iter_files_by_layer(Path(".").rglob("*.py"), GovernanceLayer.GOVERNANCE_RUNTIME):
            print(py_file)
    """
    for path in paths:
        if classify_layer(path) == layer:
            yield path


class LayerViolation(Exception):
    """Raised when a layer validation rule is violated."""
    def __init__(self, path: Path | str, expected: GovernanceLayer, actual: GovernanceLayer):
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Layer violation: {path} is {actual.name} but expected {expected.name}"
        )


def validate_layer_assignment(
    path: Path | str,
    expected: GovernanceLayer,
    strict: bool = True
) -> bool:
    """
    Validate that a path belongs to the expected layer.
    
    Args:
        path: The path to validate
        expected: The expected governance layer
        strict: If True, raises LayerViolation on mismatch
        
    Returns:
        True if validation passes
        
    Raises:
        LayerViolation: If strict=True and layer doesn't match
    """
    actual = classify_layer(path)
    
    if actual == expected:
        return True
    
    if strict:
        raise LayerViolation(path, expected, actual)
    
    return False


def get_layer_stats(paths: Iterator[Path]) -> dict:
    """
    Get statistics about layer distribution of paths.
    
    Returns:
        Dict mapping layer names to counts
    """
    stats: dict[str, int] = {layer.name: 0 for layer in GovernanceLayer}
    
    for path in paths:
        layer = classify_layer(path)
        stats[layer.name] += 1
    
    return stats
