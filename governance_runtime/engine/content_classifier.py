"""
Content Classification Module - Wave 3

Defines what constitutes "governance_static_content" - human-readable content
that is NOT:
- Executable code (runtime)
- Machine-readable specs (spec classifier)
- Commands (command surface)

This module provides classification functions to identify content files
that must be separated from runtime and spec.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path


# Content file patterns - human-readable, non-executable content
# This IS the authoritative source of truth for content classification
CONTENT_PATTERNS: frozenset = frozenset({
    # Root level content files
    "rules.md",
    "master.md",
    "README.md",
    "README-OPENCODE.md",
    "README-RULES.md",
    "ADR.md",
    "CHANGELOG.md",
    "QUALITY_INDEX.md",
    "SCOPE-AND-CONTEXT.md",
    "SESSION_STATE_SCHEMA.md",
    "BOOTSTRAP.md",
    "STABILITY_SLA.md",
    "TICKET_RECORD_TEMPLATE.md",
    "CONFLICT_RESOLUTION.md",
    "HowTo_Release.txt",
    "LICENSE",
    # Content directories (legacy)
    "docs",
    "docs/contracts",
    "profiles",
    "templates",
    "templates/github-actions",
    # Content directories (new Wave 15)
    "governance_content",
})

# Runtime file extensions - these are NEVER content
RUNTIME_EXTENSIONS: frozenset = frozenset({
    ".py",
    ".sh",
    ".cmd",
    ".mjs",
    ".js",
})


def _is_plugin_file(path: Path) -> bool:
    """Check if file is an OpenCode plugin (own layer, not runtime)."""
    path_str = str(path)
    # Check both old path (opencode-plugins) and new path (opencode/plugins)
    return "opencode-plugins" in path_str or "/plugins/" in path_str


def _is_runtime_file_internal(path: Path) -> bool:
    """Internal: check if file is runtime (executable code)."""
    # GitHub workflows are runtime
    if path.parts[0:2] == (".github", "workflows"):
        if path.suffix in {".yml", ".yaml"}:
            return True
    
    # Plugins are their own layer, not runtime
    if _is_plugin_file(path):
        return False
    
    return path.suffix in RUNTIME_EXTENSIONS


def is_content_file(path: Path) -> bool:
    """
    Determine if a file is governance content (human-readable, non-executable).
    
    Classification rules:
    1. Exact match in CONTENT_PATTERNS (authoritative)
    2. File in a directory that matches CONTENT_PATTERNS
    3. EXCLUDE: runtime files (.py, .sh, .cmd, .mjs, .js)
    4. EXCLUDE: spec files (see spec_classifier)
    
    Content is NOT:
    - Executable code (.py, .sh, .cmd)
    - Machine specs (.yaml, .yml, .json) - use spec_classifier
    - Commands (see command surface)
    """
    from governance.engine.spec_classifier import is_spec_file as is_spec
    
    path = Path(path.as_posix() if hasattr(path, 'as_posix') else str(path))
    path_str = path.as_posix()
    
    # First: check if it's runtime - never content
    if _is_runtime_file_internal(path):
        return False
    
    # Second: check if it's spec - not content
    if is_spec(path):
        return False
    
    # Third: check exact file matches in CONTENT_PATTERNS
    if path_str in CONTENT_PATTERNS:
        return True
    
    # Fourth: check if file is in a content directory
    for parent in path.parents:
        parent_str = parent.as_posix()
        if parent_str in CONTENT_PATTERNS:
            return True
    
    return False


def is_content_directory(path: Path) -> bool:
    """
    Determine if a directory is a content directory.
    
    A directory is content ONLY if it exactly matches a CONTENT_PATTERNS entry.
    """
    path = Path(path.as_posix() if hasattr(path, 'as_posix') else str(path))
    path_str = path.as_posix()
    
    # Exact match only
    return path_str in CONTENT_PATTERNS


def is_runtime_file(path: Path) -> bool:
    """
    Determine if a file is governance runtime (executable code).
    
    Runtime files are:
    - Python files (.py)
    - Shell scripts (.sh)
    - Batch files (.cmd)
    - JavaScript modules (.mjs, .js) - except plugins
    - Workflow files (.yml, .yaml) in .github/workflows/
    
    Note: OpenCode plugins are their own layer, not runtime.
    """
    return _is_runtime_file_internal(path)


def get_content_paths(repo_root: Path) -> list[Path]:
    """
    Get all content paths under a repository root.
    
    This is a CURATED scanner - it only searches known content locations
    defined in CONTENT_PATTERNS, excluding runtime and spec.
    """
    content_paths = []
    
    # Scan each content directory from CONTENT_PATTERNS
    for pattern in CONTENT_PATTERNS:
        content_path = repo_root / pattern
        
        if not content_path.exists():
            continue
            
        if content_path.is_file():
            # Root-level content file
            if is_content_file(content_path):
                content_paths.append(content_path)
        elif content_path.is_dir():
            # Content directory - scan for content files
            for item in content_path.rglob("*"):
                if item.is_file() and is_content_file(item):
                    content_paths.append(item)
    
    return sorted(content_paths)
