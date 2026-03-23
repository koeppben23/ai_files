"""
Governance Layer Enforcement Module - Wave 8

This module provides enforcement and validation of governance layer boundaries.
It ensures that files are in the correct layers and that layer rules are respected.

Key features:
- Layer boundary validation
- Cross-layer reference checking
- Packaging rule enforcement
- State file location validation

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Iterator, Iterable

from governance_runtime.layers import (
    GovernanceLayer,
    classify_layer,
    is_static_content_payload,
    is_installable_layer,
    is_state_file as layers_is_state_file,
    is_log_file as layers_is_log_file,
)
from governance_runtime.engine import state_classifier


class ViolationType(Enum):
    """
    Types of layer violations.
    
    Currently implemented:
    - STATE_NOT_IN_WORKSPACE: State file not in workspaces/ or state dir
    - LOG_NOT_IN_VALID_LOCATION: Log file not under workspaces/<fp>/logs/
    - PACKAGING_VIOLATION: File that shouldn't be packaged
    - UNKNOWN_FILE: Cannot determine layer
    
    Reserved for future waves:
    - INVALID_LAYER: File assigned to wrong layer (future)
    - CROSS_LAYER_REFERENCE: Invalid cross-layer reference (future)
    """
    INVALID_LAYER = auto()      # Reserved for future
    STATE_NOT_IN_WORKSPACE = auto()
    LOG_NOT_IN_VALID_LOCATION = auto()
    PACKAGING_VIOLATION = auto()
    CROSS_LAYER_REFERENCE = auto()  # Reserved for future
    UNKNOWN_FILE = auto()


@dataclass
class LayerViolation:
    """Represents a single layer violation."""
    path: str
    violation_type: ViolationType
    message: str
    expected: GovernanceLayer | None = None
    actual: GovernanceLayer | None = None


@dataclass
class EnforcementResult:
    """Result of layer enforcement check."""
    passed: bool
    violations: list[LayerViolation]
    total_files_checked: int = 0


def check_layer_assignment(path: Path | str) -> LayerViolation | None:
    """
    Check if a path has a valid layer assignment.
    
    Returns None if valid, otherwise returns a LayerViolation.
    """
    layer = classify_layer(path)
    
    if layer == GovernanceLayer.UNKNOWN:
        return LayerViolation(
            path=str(path),
            violation_type=ViolationType.UNKNOWN_FILE,
            message=f"Cannot determine layer for: {path}",
        )
    
    return None


def check_state_file_location(path: Path | str) -> LayerViolation | None:
    """
    Check if a state file is in a valid location.
    
    State files must be under workspaces/<fp>/ or in recognized state directories.
    Log files MUST be under workspaces/<fp>/logs/ specifically.
    
    This check runs regardless of current classification - if a file has a
    state/log filename, we validate its location even if misclassified.
    """
    if isinstance(path, Path):
        path_str = path.as_posix()
        name = path.name
    else:
        path_str = path
        name = path.split("/")[-1]
    
    if not layers_is_state_file(name) and not layers_is_log_file(name):
        return None
    
    if layers_is_log_file(name):
        if not state_classifier.is_valid_log_location(path_str):
            return LayerViolation(
                path=str(path),
                violation_type=ViolationType.LOG_NOT_IN_VALID_LOCATION,
                message=f"Log file must be under workspaces/<fp>/logs/: {path}",
                expected=None,
                actual=classify_layer(path),
            )
    
    if layers_is_state_file(name):
        layer = classify_layer(path)
        if layer != GovernanceLayer.REPO_RUN_STATE:
            return LayerViolation(
                path=str(path),
                violation_type=ViolationType.STATE_NOT_IN_WORKSPACE,
                message=f"State file must be under workspaces/ or state directory: {path}",
                expected=None,
                actual=layer,
            )
    
    return None


def check_packaging_rules(path: Path | str) -> LayerViolation | None:
    """
    Check if a path violates packaging rules.
    
    Rules:
    - repo_run_state files should never be packaged
    
    Note: This violation doesn't have an "expected" layer because the file
    is correctly classified - it just shouldn't be included in packages.
    """
    layer = classify_layer(path)
    
    if layer == GovernanceLayer.REPO_RUN_STATE:
        return LayerViolation(
            path=str(path),
            violation_type=ViolationType.PACKAGING_VIOLATION,
            message=f"State file should not be packaged: {path}",
            expected=None,
            actual=layer,
        )
    
    return None


def enforce_layers(
    paths: Iterable[Path | str],
    check_unknown: bool = True,
    check_state_location: bool = True,
    check_packaging: bool = True,
) -> EnforcementResult:
    """
    Enforce layer rules on a collection of paths.
    
    Args:
        paths: Paths to check
        check_unknown: Whether to flag unknown layers as violations
        check_state_location: Whether to validate state file locations
        check_packaging: Whether to check packaging rules
        
    Returns:
        EnforcementResult with pass/fail status and any violations
    """
    violations: list[LayerViolation] = []
    total = 0
    
    for path in paths:
        total += 1
        
        if check_unknown:
            v = check_layer_assignment(path)
            if v:
                violations.append(v)
                continue
        
        if check_state_location:
            v = check_state_file_location(path)
            if v:
                violations.append(v)
                continue
        
        if check_packaging:
            v = check_packaging_rules(path)
            if v:
                violations.append(v)
    
    return EnforcementResult(
        passed=len(violations) == 0,
        violations=violations,
        total_files_checked=total,
    )


def get_layer_distribution(paths: Iterable[Path | str]) -> dict[GovernanceLayer, int]:
    """
    Get distribution of paths across layers.
    
    Returns:
        Dict mapping each layer to its count
    """
    distribution: dict[GovernanceLayer, int] = {layer: 0 for layer in GovernanceLayer}
    
    for path in paths:
        layer = classify_layer(path)
        distribution[layer] += 1
    
    return distribution


def generate_layer_report(
    paths: Iterable[Path | str],
    check_packaging: bool = True,
) -> str:
    """
    Generate a human-readable layer report.
    
    Args:
        paths: Paths to analyze
        check_packaging: Whether to include packaging analysis
        
    Returns:
        Formatted report string
    """
    distribution = get_layer_distribution(paths)
    
    lines = ["Governance Layer Report", "=" * 50, ""]
    
    for layer, count in distribution.items():
        layer_name = layer.name
        percentage = (count / sum(distribution.values())) * 100 if sum(distribution.values()) > 0 else 0
        lines.append(f"  {layer_name}: {count} ({percentage:.1f}%)")
    
    lines.append("")
    
    if check_packaging:
        installable = sum(
            count for layer, count in distribution.items() 
            if is_installable_layer(layer)
        )
        static_payload = sum(
            count for layer, count in distribution.items() 
            if is_static_content_payload(layer)
        )
        
        lines.append("Packaging Summary:")
        lines.append(f"  Installable: {installable}")
        lines.append(f"  Static payload: {static_payload}")
        lines.append("")
    
    return "\n".join(lines)
