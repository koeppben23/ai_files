"""
Governance Paths Package

Provides path resolution for governance layers.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from governance.paths.layer_adapter import (
    get_config_root,
    get_opencode_command_root,
    get_governance_runtime_root,
    get_governance_content_root,
    get_governance_spec_root,
    get_workspace_root,
    get_workspace_logs_root,
    get_workspace_state_root,
    resolve_legacy_path,
    set_config_root_override,
    # Dual-read resolvers for installer (Wave 15.2)
    get_governance_docs_root,
    get_profiles_root,
    get_templates_root,
    get_rulesets_root,
)

__all__ = [
    "get_config_root",
    "get_opencode_command_root",
    "get_governance_runtime_root",
    "get_governance_content_root",
    "get_governance_spec_root",
    "get_workspace_root",
    "get_workspace_logs_root",
    "get_workspace_state_root",
    "resolve_legacy_path",
    "set_config_root_override",
    # Dual-read resolvers for installer (Wave 15.2)
    "get_governance_docs_root",
    "get_profiles_root",
    "get_templates_root",
    "get_rulesets_root",
]
