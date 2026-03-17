"""
Path Adapter Layer - Wave 1

Central resolver for governance layer paths.
Provides logical roots for:
- opencode_command_root
- governance_runtime_root
- governance_content_root
- governance_spec_root
- workspace_state_root

This adapter enables future physical separation without code changes.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


# Environment variable overrides (for testing/migration)
_OPENCODE_CONFIG_ROOT: Optional[str] = None


def set_config_root_override(path: str | None) -> None:
    """Set override for config root (testing only)."""
    global _OPENCODE_CONFIG_ROOT
    _OPENCODE_CONFIG_ROOT = path


def get_config_root() -> Path:
    """Get the OpenCode config root."""
    if _OPENCODE_CONFIG_ROOT:
        return Path(_OPENCODE_CONFIG_ROOT)
    env_root = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_root:
        return Path(env_root)
    # Default fallback
    return Path.home() / ".config" / "opencode"


def get_opencode_command_root() -> Path:
    """Get the OpenCode commands root (where rails live)."""
    return get_config_root() / "commands"


def get_governance_runtime_root() -> Path:
    """Get the governance runtime root."""
    # Current layout: runtime lives under commands/governance
    # Future: will be separate
    return get_config_root() / "commands" / "governance"


def get_governance_content_root() -> Path:
    """Get the governance content root (docs, profiles, templates)."""
    # Current layout: content is mixed under commands/
    # Future: will be separate
    return get_config_root() / "commands"


def get_governance_spec_root() -> Path:
    """Get the governance spec root (machine SSOT files)."""
    # Current layout: spec is mixed under commands/governance/
    # Future: will be separate
    return get_config_root() / "commands" / "governance"


def get_workspace_root(repo_fingerprint: str) -> Path:
    """Get the workspace root for a specific repository."""
    return get_config_root() / "workspaces" / repo_fingerprint


def get_workspace_logs_root(repo_fingerprint: str) -> Path:
    """
    Get the logs root for a specific workspace.
    
    HARD RULE: Logs MUST only reside under workspaces/<fp>/logs/
    """
    return get_workspace_root(repo_fingerprint) / "logs"


def get_workspace_state_root(repo_fingerprint: str) -> Path:
    """Get the state root for a specific workspace."""
    return get_workspace_root(repo_fingerprint)


# Legacy path mappings for backward compatibility during migration
# Order matters: more specific paths first
LEGACY_PATH_MAPPINGS = [
    # New structure (Wave 15)
    ("opencode/commands", get_opencode_command_root),
    ("opencode/plugins", lambda: get_config_root() / "plugins"),
    ("governance_runtime", get_governance_runtime_root),
    ("governance_content", get_governance_content_root),
    ("governance_spec", get_governance_spec_root),
    # Old structure (for backward compatibility)
    ("commands/governance", get_governance_runtime_root),
    ("commands/docs", lambda: get_governance_content_root() / "docs"),
    ("commands/profiles", lambda: get_governance_content_root() / "profiles"),
    # Base paths last
    ("commands", get_opencode_command_root),
]


def resolve_legacy_path(legacy_path: str) -> Path:
    """
    Resolve a legacy path to its new logical location.
    
    This enables dual-read during migration.
    
    Preserves the suffix after the matched prefix.
    Example: "commands/governance/engine/x.py" -> <runtime_root>/engine/x.py
    """
    # Normalize path
    legacy_path = legacy_path.replace("\\", "/").strip("/")
    
    # Check known mappings (more specific first)
    for prefix, resolver in LEGACY_PATH_MAPPINGS:
        prefix = prefix.strip("/")
        if legacy_path == prefix:
            # Exact match - no suffix
            return resolver()
        if legacy_path.startswith(prefix + "/"):
            # Has suffix - preserve it
            suffix = legacy_path[len(prefix):]
            resolved = resolver()
            # Join carefully to avoid double slashes
            suffix = suffix.lstrip("/")
            return resolved / suffix
    
    # Default: fall back to commands root
    return get_opencode_command_root()
