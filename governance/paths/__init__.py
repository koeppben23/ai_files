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
]
