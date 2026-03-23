"""
Governance Path Contract Module - Wave 10

This module provides path contract validation - ensuring that paths conform
to the governance layer system rules with real structure enforcement.

Key features:
- Layer assignment validation
- Directory structure enforcement (not just a placeholder!)
- State location validation
- Packaging rule enforcement
- Contract violation reporting

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Iterator, Iterable

from governance_runtime.layers import (
    GovernanceLayer,
    classify_layer,
)
from governance_runtime.enforce import enforce_layers, get_layer_distribution, ViolationType


class ContractRule(Enum):
    """Rules for path contract validation."""
    LAYER_ASSIGNMENT = auto()
    STATE_LOCATION = auto()
    PACKAGING = auto()
    DIRECTORY_STRUCTURE = auto()


@dataclass
class PathContractViolation:
    """Represents a single path contract violation."""
    path: str
    rule: ContractRule
    message: str
    severity: str = "error"


@dataclass
class PathContractResult:
    """Result of path contract validation."""
    passed: bool
    violations: list[PathContractViolation]
    total_paths_checked: int = 0
    layer_distribution: dict[GovernanceLayer, int] = field(default_factory=dict)


ALLOWED_PREFIXES: dict[GovernanceLayer, tuple[str, ...]] = {
    GovernanceLayer.OPENCODE_INTEGRATION: (
        "commands/",
        "plugins/",
        "opencode/commands/",
        "opencode/plugins/",
    ),
    GovernanceLayer.GOVERNANCE_RUNTIME: (
        "governance_runtime/",
        "governance_runtime/",
    ),
    GovernanceLayer.GOVERNANCE_CONTENT: (
        "",
        "docs/",
        "profiles/",
        "templates/",
        "governance_content/",
    ),
    GovernanceLayer.GOVERNANCE_SPEC: (
        "",
        "schemas/",
        "governance_runtime/contracts/",
        "governance_runtime/receipts/",
        "governance_runtime/assets/schemas/",
        "governance_spec/",
    ),
    GovernanceLayer.REPO_RUN_STATE: (
        "workspaces/",
        ".lock/",
    ),
}


def check_directory_structure(path: Path | str) -> PathContractViolation | None:
    """
    Check if a path follows the expected directory structure for its layer.
    
    This is the real DIRECTORY_STRUCTURE validation - not just a placeholder.
    """
    if isinstance(path, Path):
        path_str = path.as_posix()
    else:
        path_str = path
    
    layer = classify_layer(path_str)
    
    if layer == GovernanceLayer.UNKNOWN:
        return None
    
    if layer not in ALLOWED_PREFIXES:
        return None
    
    allowed = ALLOWED_PREFIXES[layer]
    
    for prefix in allowed:
        if prefix == "":
            if "/" not in path_str and path_str:
                return None
        elif path_str.startswith(prefix):
            return None
    
    expected = ", ".join(allowed) if allowed else "any"
    return PathContractViolation(
        path=path_str,
        rule=ContractRule.DIRECTORY_STRUCTURE,
        message=f"{layer.name} files must be under {expected}, found: {path_str}",
    )


def validate_directory_structure(
    paths: Iterable[Path | str],
) -> list[PathContractViolation]:
    """
    Validate directory structure for all paths.
    
    Returns violations for paths that don't follow layer structure rules.
    """
    violations = []
    for path in paths:
        v = check_directory_structure(path)
        if v:
            violations.append(v)
    return violations


def validate_path_contract(
    root: Path | str,
    check_layer: bool = True,
    check_state_location: bool = True,
    check_packaging: bool = True,
    check_dir_structure: bool = True,
) -> PathContractResult:
    """
    Validate all paths under a root against the governance contract.
    
    Args:
        root: Root directory to validate
        check_layer: Check layer assignments
        check_state_location: Check state file locations
        check_packaging: Check packaging rules
        check_dir_structure: Check directory structure rules
        
    Returns:
        PathContractResult with validation results
    """
    root_path = Path(root) if isinstance(root, str) else root
    
    paths: list[Path] = []
    for p in root_path.rglob("*"):
        if p.is_file():
            paths.append(p)
    
    layer_dist = get_layer_distribution(paths)
    
    violations: list[PathContractViolation] = []
    
    if check_layer or check_state_location or check_packaging:
        enforcement_result = enforce_layers(
            paths,
            check_unknown=check_layer,
            check_state_location=check_state_location,
            check_packaging=check_packaging,
        )
        
        for v in enforcement_result.violations:
            if v.violation_type == ViolationType.UNKNOWN_FILE:
                rule = ContractRule.LAYER_ASSIGNMENT
            elif v.violation_type == ViolationType.STATE_NOT_IN_WORKSPACE:
                rule = ContractRule.STATE_LOCATION
            elif v.violation_type == ViolationType.LOG_NOT_IN_VALID_LOCATION:
                rule = ContractRule.STATE_LOCATION
            elif v.violation_type == ViolationType.PACKAGING_VIOLATION:
                rule = ContractRule.PACKAGING
            else:
                rule = ContractRule.LAYER_ASSIGNMENT
            
            violations.append(PathContractViolation(
                path=v.path,
                rule=rule,
                message=v.message,
            ))
    
    if check_dir_structure:
        structure_violations = validate_directory_structure(paths)
        violations.extend(structure_violations)
    
    return PathContractResult(
        passed=len(violations) == 0,
        violations=violations,
        total_paths_checked=len(paths),
        layer_distribution=layer_dist,
    )


def validate_single_path(
    path: Path | str,
    check_layer: bool = True,
    check_state_location: bool = True,
    check_packaging: bool = True,
    check_dir_structure: bool = True,
) -> list[PathContractViolation]:
    """
    Validate a single path against the governance contract.
    
    Args:
        path: Path to validate
        check_layer: Check layer assignment
        check_state_location: Check state file location
        check_packaging: Check packaging rules
        check_dir_structure: Check directory structure
        
    Returns:
        List of violations (empty if valid)
    """
    violations = []
    path_str = str(path)
    
    if check_dir_structure:
        v = check_directory_structure(path)
        if v:
            violations.append(v)
    
    if check_layer:
        from governance_runtime.enforce import enforce_layers
        result = enforce_layers([path_str], check_unknown=True, check_packaging=False)
        for viol in result.violations:
            violations.append(PathContractViolation(
                path=viol.path,
                rule=ContractRule.LAYER_ASSIGNMENT,
                message=viol.message,
            ))
    
    if check_state_location:
        from governance_runtime.enforce import check_state_file_location
        v = check_state_file_location(path_str)
        if v:
            violations.append(PathContractViolation(
                path=v.path,
                rule=ContractRule.STATE_LOCATION,
                message=v.message,
            ))
    
    if check_packaging:
        from governance_runtime.enforce import check_packaging_rules
        v = check_packaging_rules(path_str)
        if v:
            violations.append(PathContractViolation(
                path=v.path,
                rule=ContractRule.PACKAGING,
                message=v.message,
            ))
    
    return violations


def generate_contract_report(
    root: Path | str,
    verbose: bool = False,
) -> str:
    """
    Generate a comprehensive contract report for a root directory.
    
    Args:
        root: Root directory to analyze
        verbose: Include detailed violation info
        
    Returns:
        Formatted report string
    """
    result = validate_path_contract(root)
    
    lines = [
        "Governance Path Contract Report",
        "=" * 60,
        "",
    ]
    
    if result.passed:
        lines.append("✓ All paths comply with governance contract")
    else:
        lines.append("✗ Contract violations detected")
    
    lines.extend([
        f"Total paths checked: {result.total_paths_checked}",
        "",
    ])
    
    lines.append("Layer Distribution:")
    for layer, count in result.layer_distribution.items():
        if count > 0:
            lines.append(f"  {layer.name}: {count}")
    lines.append("")
    
    if result.violations and verbose:
        lines.append("Violations:")
        by_rule: dict[ContractRule, list[PathContractViolation]] = {}
        for v in result.violations:
            if v.rule not in by_rule:
                by_rule[v.rule] = []
            by_rule[v.rule].append(v)
        
        for rule, rule_violations in by_rule.items():
            lines.append(f"  {rule.name} ({len(rule_violations)}):")
            for v in rule_violations:
                lines.append(f"    - {v.path}")
                lines.append(f"      {v.message}")
            lines.append("")
    
    return "\n".join(lines)


def get_allowed_prefixes_for_layer(layer: GovernanceLayer) -> tuple[str, ...]:
    """
    Get the allowed directory prefixes for a layer.
    
    Returns a tuple of allowed path prefixes for machine verification.
    """
    return ALLOWED_PREFIXES.get(layer, ())


def get_expected_directory_for_layer(layer: GovernanceLayer) -> str:
    """
    Get the expected directory for a given layer.
    
    Returns human-readable description of expected locations.
    """
    prefixes = get_allowed_prefixes_for_layer(layer)
    
    if not prefixes:
        return "none"
    
    formatted = []
    for p in prefixes:
        if p == "":
            formatted.append("root level")
        else:
            formatted.append(p.rstrip("/"))
    
    return ", ".join(formatted)
