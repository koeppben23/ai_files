"""
Unified Layer Classification Module - Wave 6

Provides a single interface to classify any path into its governance layer.

Layers:
- opencode_integration: Only TRUE slash commands (not content references)
- governance_runtime: Python code (executable logic)
- governance_content: Human-readable docs, profiles, templates, and NON-command references
- governance_spec: Machine-readable SSOT (specs, schemas, contracts)
- repo_run_state: Runtime state and logs (per-repo, never packaged)

IMPORTANT: master.md and rules.md are CONTENT, NOT commands.
They belong in governance_content, NOT opencode_integration.

This module is the integration point that ties together:
- spec_classifier (Wave 2)
- content_classifier (Wave 3)
- command_surface (Wave 4)
- state_classifier (Wave 5)

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path
from enum import Enum, auto

from governance.engine import spec_classifier
from governance.engine import content_classifier
from governance.engine import command_surface
from governance.engine import state_classifier


class GovernanceLayer(Enum):
    """Enumeration of governance layers for classification."""
    OPENCODE_INTEGRATION = auto()
    GOVERNANCE_RUNTIME = auto()
    GOVERNANCE_CONTENT = auto()
    GOVERNANCE_SPEC = auto()
    REPO_RUN_STATE = auto()
    UNKNOWN = auto()


def classify_layer(path: Path | str) -> GovernanceLayer:
    """
    Classify a path into its governance layer.
    
    Priority order (first match wins):
    1. repo_run_state (state files take precedence)
    2. opencode_integration (ONLY canonical commands - not content references)
    3. governance_spec (machine-readable SSOT)
    4. governance_content (human-readable, including master.md, rules.md)
    5. governance_runtime (executable code)
    """
    if isinstance(path, Path):
        path_obj = path
        path_str = path.as_posix()
    else:
        path_obj = Path(path)
        path_str = path
    
    basename = path_str.split("/")[-1] if "/" in path_str else path_str
    
    if state_classifier.is_state_file(basename):
        return GovernanceLayer.REPO_RUN_STATE
    
    if state_classifier.is_state_directory(path_str):
        return GovernanceLayer.REPO_RUN_STATE
    
    if state_classifier.is_log_file(basename):
        return GovernanceLayer.REPO_RUN_STATE
    
    if command_surface.is_canonical_command(basename):
        return GovernanceLayer.OPENCODE_INTEGRATION
    
    if spec_classifier.is_spec_file(path_obj):
        return GovernanceLayer.GOVERNANCE_SPEC
    
    if spec_classifier.is_spec_directory(path_obj):
        return GovernanceLayer.GOVERNANCE_SPEC
    
    if content_classifier.is_content_file(path_obj):
        return GovernanceLayer.GOVERNANCE_CONTENT
    
    if content_classifier.is_content_directory(path_obj):
        return GovernanceLayer.GOVERNANCE_CONTENT
    
    if content_classifier.is_content_file(Path(basename)):
        return GovernanceLayer.GOVERNANCE_CONTENT
    
    if content_classifier.is_content_directory(Path(basename)):
        return GovernanceLayer.GOVERNANCE_CONTENT
    
    # Plugins are OPENCODE_INTEGRATION
    if content_classifier._is_plugin_file(path_obj):
        return GovernanceLayer.OPENCODE_INTEGRATION
    
    if content_classifier.is_runtime_file(path_obj):
        return GovernanceLayer.GOVERNANCE_RUNTIME
    
    return GovernanceLayer.UNKNOWN


def get_layer_name(layer: GovernanceLayer) -> str:
    """Get human-readable layer name."""
    return {
        GovernanceLayer.OPENCODE_INTEGRATION: "opencode_integration",
        GovernanceLayer.GOVERNANCE_RUNTIME: "governance_runtime",
        GovernanceLayer.GOVERNANCE_CONTENT: "governance_content",
        GovernanceLayer.GOVERNANCE_SPEC: "governance_spec",
        GovernanceLayer.REPO_RUN_STATE: "repo_run_state",
        GovernanceLayer.UNKNOWN: "unknown",
    }[layer]


def is_static_content_payload(layer: GovernanceLayer) -> bool:
    """
    Determine if a layer belongs in the static content/spec payload.
    
    This is the "pure governance payload" - content and specs that can be
    distributed as static files without installation.
    """
    return layer in {
        GovernanceLayer.GOVERNANCE_CONTENT,
        GovernanceLayer.GOVERNANCE_SPEC,
    }


def is_installable_layer(layer: GovernanceLayer) -> bool:
    """
    Determine if a layer's files can be installed to a user's environment.
    
    All layers except REPO_RUN_STATE can be installed. UNKNOWN is excluded.
    """
    return layer not in {
        GovernanceLayer.REPO_RUN_STATE,
        GovernanceLayer.UNKNOWN,
    }
