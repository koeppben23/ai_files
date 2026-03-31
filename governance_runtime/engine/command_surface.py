"""
Command Surface Module - Wave 4

Defines the canonical command surface for OpenCode.

This module provides authoritative classification of which files
are ACTUAL COMMANDS vs content that happens to be in the commands directory.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path


# CANONICAL COMMANDS - these are the ONLY true slash commands
# All other files in the commands/ directory are content, not commands
CANONICAL_COMMANDS: frozenset = frozenset({
    "continue.md",
    "hydrate.md",
    "plan.md",
    "review.md",
    "review-decision.md",
    "ticket.md",
    "implement.md",
    "implementation-decision.md",
    "audit-readout.md",
})

# NON-COMMAND FILES - files that appear in commands/ but are NOT commands
# These are content that happens to be referenced by OpenCode, not slash commands
NON_COMMAND_FILES: frozenset = frozenset({
    "master.md",        # Governance master guidance, NOT a command
    "rules.md",         # Governance rulebook, NOT a command
    "SESSION_STATE_SCHEMA.md",  # Schema documentation, NOT a command
    "README-OPENCODE.md",       # User guide, NOT a command
})

# DEPRECATED ALIASES - old command names that should not be used
DEPRECATED_COMMANDS: frozenset = frozenset({
    "resume.md",        # Deprecated alias for continue
    "resume_prompt.md", # Deprecated alias for continue
    "audit.md",        # Deprecated alias for audit-readout
})


def is_canonical_command(path: Path | str) -> bool:
    """
    Determine if a file is a canonical OpenCode command.
    
    Only files in CANONICAL_COMMANDS are true slash commands.
    All other files (even if in commands/ directory) are content.
    """
    if isinstance(path, Path):
        path = path.name
    return path in CANONICAL_COMMANDS


def is_non_command_file(path: Path | str) -> bool:
    """
    Determine if a file is explicitly NOT a command.
    
    These are content files that happen to be referenced by OpenCode
    but are NOT slash commands.
    """
    if isinstance(path, Path):
        path = path.name
    return path in NON_COMMAND_FILES


def is_command_surface_file(path: Path | str) -> bool:
    """
    Determine if a file belongs to the command surface.
    
    Returns True for:
    - Canonical commands
    - Non-command files that are referenced by OpenCode
    
    Returns False for:
    - Deprecated aliases
    - Content that happens to be in commands/ directory
    """
    if isinstance(path, Path):
        path = path.name
    return is_canonical_command(path) or is_non_command_file(path)


def is_deprecated_command(path: Path | str) -> bool:
    """Check if a command is deprecated."""
    if isinstance(path, Path):
        path = path.name
    return path in DEPRECATED_COMMANDS


def get_all_command_surface_files() -> list[str]:
    """Get all files that belong to the command surface (canonical + non-command)."""
    return sorted(CANONICAL_COMMANDS | NON_COMMAND_FILES)
