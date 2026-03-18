"""
State and Logs Classification Module - Wave 5

Defines what constitutes "repo_run_state" - runtime state that should
NEVER be packaged as static install content.

This module enforces the hard rule:
- Logs MUST only reside under workspaces/<fp>/logs/
- No global logs/ directory for runtime logs

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path


# State file patterns - runtime state that should NEVER be installed
# These are generated per-repo-run and must be excluded from packaging
STATE_PATTERNS: frozenset = frozenset({
    # Workspace state files
    "SESSION_STATE.json",
    "events.jsonl",
    "flow.log.jsonl",
    "error.log.jsonl",
    "targeted_checks.log",
    "repo-identity-map.yaml",
    "repo-cache.yaml",
    "repo-map-digest.md",
    "workspace-memory.yaml",
    "decision-pack.md",
    "business-rules.md",
    "business-rules-status.md",
    "plan-record.json",
    "current_run.json",
    "marker.json",
    # Install-time generated
    "INSTALL_HEALTH.json",
    "INSTALL_MANIFEST.json",
    "governance.paths.json",
    "governance.activation_intent.json",
})

# State directories - directories that contain state files
STATE_DIR_PATTERNS: frozenset = frozenset({
    "workspaces",
    ".lock",
    "plan-record-archive",
    "evidence",
    "runs",
})

# Log file patterns
LOG_PATTERNS: frozenset = frozenset({
    "flow.log.jsonl",
    "error.log.jsonl",
    "boot.log.jsonl",
    "targeted_checks.log",
})


def is_state_file(path: Path | str) -> bool:
    """
    Determine if a file is runtime state (should NEVER be packaged).
    
    State files are:
    - Session state files (SESSION_STATE.json)
    - Event logs (events.jsonl)
    - Flow logs (flow.log.jsonl)
    - Error logs (error.log.jsonl)
    - Install health/manifest
    - Workspace artifacts
    
    These files MUST be excluded from packaging.
    """
    if isinstance(path, Path):
        path = path.name
    return path in STATE_PATTERNS


def is_state_directory(path: Path | str) -> bool:
    """
    Determine if a directory contains state files.
    
    State directories are:
    - workspaces/ (contains per-repo state)
    - .lock/ (runtime locks)
    - plan-record-archive/ (archived state)
    """
    if isinstance(path, Path):
        path = path.name
    return path in STATE_DIR_PATTERNS


def is_log_file(path: Path | str) -> bool:
    """
    Determine if a file is a log file.
    
    Log files must ONLY reside under workspaces/<fp>/logs/
    """
    if isinstance(path, Path):
        path = path.name
    return path in LOG_PATTERNS


def is_workspace_path(path: Path | str) -> bool:
    """
    Determine if a path is under a workspace.
    
    This is the ONLY valid location for logs and runtime state.
    Uses proper path segment matching to avoid false positives.
    """
    if isinstance(path, Path):
        path_str = path.as_posix()
    else:
        path_str = path
    
    path_parts = path_str.split("/")
    for i, part in enumerate(path_parts):
        if part == "workspaces" and i + 1 < len(path_parts):
            return True
    
    return False


def is_valid_log_location(path: Path | str) -> bool:
    """
    Check if a log file is in a valid location.
    
    HARD RULE: Logs MUST only be under workspaces/<fp>/logs/
    - No logs in workspace root
    - No logs in other directories
    """
    if isinstance(path, Path):
        path_str = path.as_posix()
    else:
        path_str = path
    
    if not is_workspace_path(path):
        return False
    
    if "/logs/" in path_str:
        return True
    
    return False


def is_install_artifact(path: Path | str) -> bool:
    """
    Determine if a file is an install-time generated artifact.
    
    These are created by the installer and should not be packaged.
    """
    if isinstance(path, Path):
        path = path.name
    return path in {
        "INSTALL_HEALTH.json",
        "INSTALL_MANIFEST.json",
        "governance.paths.json",
        "governance.activation_intent.json",
    }
