"""
Governance System - Consolidated Public API

This package provides the complete governance layer classification and enforcement system.

Layers:
- opencode_integration: Only TRUE slash commands
- governance_runtime: Python code (executable logic)
- governance_content: Human-readable docs, profiles, templates
- governance_spec: Machine-readable SSOT
- repo_run_state: Runtime state and logs (never packaged)

Quick Start:
    from governance import classify_layer, GovernanceLayer
    
    layer = classify_layer("commands/continue.md")
    if layer == GovernanceLayer.OPENCODE_INTEGRATION:
        print("This is a command!")

Modules:
- governance.layers: Core classification API
- governance.enforce: Layer boundary validation
- governance.contract: Path contract validation
- governance.installer: Installer integration layer

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from governance.layers import (
    GovernanceLayer,
    classify_layer,
    get_layer_name,
    is_static_content_payload,
    is_installable_layer,
    is_state_file,
    is_log_file,
    is_command,
    is_spec_file,
    is_content_file,
    is_runtime_file,
    get_layer_for_path,
    iter_files_by_layer,
    validate_layer_assignment,
    get_layer_stats,
    LayerViolation,
)

from governance.enforce import (
    ViolationType,
    EnforcementResult,
    check_layer_assignment,
    check_state_file_location,
    check_packaging_rules,
    enforce_layers,
    generate_layer_report,
    get_layer_distribution,
)

from governance.contract import (
    ContractRule,
    PathContractViolation,
    PathContractResult,
    validate_path_contract,
    validate_single_path,
    generate_contract_report,
    get_expected_directory_for_layer,
    get_allowed_prefixes_for_layer,
    check_directory_structure,
    validate_directory_structure,
)

from governance.installer import (
    collect_by_layer,
    collect_installable,
    collect_static_payload,
    is_installable_path,
    get_layer_info,
    exclude_state_files,
)

from governance.structure import (
    DirectoryType,
    StructureRule,
    STRUCTURE_RULES,
    get_directory_type,
    is_valid_structure,
    get_legacy_paths,
    validate_directory_structure,
    get_structure_summary,
)

__all__ = [
    # Layer classification
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
    "get_layer_stats",
    # Enforcement
    "ViolationType",
    "LayerViolation",
    "EnforcementResult",
    "check_layer_assignment",
    "check_state_file_location",
    "check_packaging_rules",
    "enforce_layers",
    "generate_layer_report",
    "get_layer_distribution",
    # Contract
    "ContractRule",
    "PathContractViolation",
    "PathContractResult",
    "validate_path_contract",
    "validate_single_path",
    "generate_contract_report",
    "get_expected_directory_for_layer",
    "get_allowed_prefixes_for_layer",
    "check_directory_structure",
    "validate_directory_structure",
    # Structure
    "DirectoryType",
    "StructureRule",
    "STRUCTURE_RULES",
    "get_directory_type",
    "is_valid_structure",
    "get_legacy_paths",
    "get_structure_summary",
    # Installer integration
    "collect_by_layer",
    "collect_installable",
    "collect_static_payload",
    "is_installable_path",
    "get_layer_info",
    "exclude_state_files",
]
