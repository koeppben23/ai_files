#!/usr/bin/env python3
"""Semantic Discovery — SSOTs, Invariants, Conventions, Patterns.

Pass 2b: Semantic Discovery (interpretive, knowledge-based)

This module provides structured discovery of repository semantics:
- SSOTs (Sources of Single Truth): Authoritative sources for specific concerns
- Invariants: Rules/conditions that must always be true
- Conventions: Established patterns and standards in the codebase
- Patterns: Recurring structural/code patterns

The discovery is designed to be:
- Conservative: Better to miss a fact than report a wrong one
- Evidence-based: Every fact has source and confidence level
- Useful for ticket quality: Focus on "where is truth?", "what must not break?"

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Import shared types from structural discovery
from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import (
    Confidence,
    Evidence,
)


# ---------------------------------------------------------------------------
# Semantic Fact Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SSOTFact:
    """Source of Single Truth — authoritative source for a concern."""
    concern: str          # "phase-routing", "session-state", "binding-paths", etc.
    path: str             # File/directory path that is the SSOT
    authority: str        # Why this is the SSOT (e.g., "spec-ssot", "kernel-ssot")
    evidence: Evidence
    schema: str | None = None  # Schema identifier if known


@dataclass(frozen=True)
class InvariantFact:
    """Invariant — rule/condition that must always be true."""
    rule: str             # Human-readable rule description
    category: str         # "security", "data-integrity", "path-constraint", "phase-ordering"
    evidence: Evidence
    enforcement: str | None = None  # How it's enforced (e.g., "gate", "validation", "convention")


@dataclass(frozen=True)
class ConventionFact:
    """Convention — established pattern or standard in the codebase."""
    name: str             # e.g., "error-handler-pattern", "writer-naming"
    description: str      # Human-readable description
    category: str         # "naming", "structure", "error-handling", "testing", "documentation"
    evidence: Evidence
    scope: str = "global"  # "global", "module", "file-type"


@dataclass(frozen=True)
class PatternFact:
    """Pattern — recurring structural or code pattern."""
    name: str             # e.g., "fallback-import", "gate-failure-emission"
    description: str      # Human-readable description
    locations: list[str]  # File paths where pattern occurs
    category: str         # "error-handling", "import", "persistence", "validation"
    evidence: Evidence
    sample: str | None = None  # Code snippet or example


@dataclass(frozen=True)
class DefaultFact:
    """Default value or fallback behavior."""
    setting: str          # e.g., "profile", "mode", "timeout"
    value: str            # Default value
    evidence: Evidence
    override_path: str | None = None  # Where override is stored


@dataclass(frozen=True)
class DeviationFact:
    """Deviation from expected norm."""
    description: str      # What deviates
    expected: str         # What was expected
    observed: str         # What was actually found
    severity: str         # "info", "warning", "concern"
    evidence: Evidence
    recommendation: str | None = None


@dataclass(frozen=True)
class SemanticFacts:
    """Complete semantic discovery results."""
    ssots: list[SSOTFact]
    invariants: list[InvariantFact]
    conventions: list[ConventionFact]
    patterns: list[PatternFact]
    defaults: list[DefaultFact]
    deviations: list[DeviationFact]
    discovered_at: str
    discovery_version: str = "2.0"


# ---------------------------------------------------------------------------
# Constants for SSOT Detection
# ---------------------------------------------------------------------------

# Known SSOT patterns (concern -> (filename_pattern, authority, schema))
# Patterns are simple filename globs that work with Path.match()
_KNOWN_SSOTS: dict[str, list[tuple[str, str, str | None]]] = {
    "phase-routing": [
        ("phase_api.yaml", "spec-ssot", "opencode-phase-api.v1"),
        ("phase_api.yml", "spec-ssot", "opencode-phase-api.v1"),
    ],
    "binding-paths": [
        ("governance.paths.json", "installer-ssot", "opencode-governance.paths.v1"),
    ],
    "session-state": [
        ("SESSION_STATE.json", "kernel-ssot", "opencode-session-state.v1"),
    ],
    "session-pointer": [
        ("SESSION_STATE.json", "pointer-ssot", "opencode-session-pointer.v1"),
    ],
    "activation-intent": [
        ("governance.activation_intent.json", "operator-ssot", "opencode-activation-intent.v1"),
    ],
    "rulebooks": [
        ("rules.md", "content-ssot", None),
        ("master.md", "content-ssot", None),
    ],
    "business-rules-status": [
        ("business-rules-status.md", "artifact-ssot", None),
    ],
}

# Invariant patterns to detect
_INVARIANT_PATTERNS: list[tuple[str, str, str, str | None]] = [
    # (pattern_to_search, rule_description, category, enforcement)
    (r"configRoot.*outside.*repo", "Config root must be outside repository root", "path-constraint", "gate"),
    (r"fingerprint.*24.*hex", "Repository fingerprint must be 24-hex format", "data-integrity", "validation"),
    (r"SESSION_STATE.*must.*exist", "SESSION_STATE file must exist before persistence", "data-integrity", "gate"),
    (r"Phase.*1\.3.*mandatory", "Phase 1.3 (Rulebook Load) is mandatory before Phase 2+", "phase-ordering", "gate"),
]

# Convention patterns
_NAMING_CONVENTIONS: list[tuple[str, str, str, str]] = [
    (r"test_.*\.py", "test-naming", "Python test files use test_*.py naming", "naming"),
    (r".*\.md$", "markdown-docs", "Documentation uses Markdown format", "documentation"),
    (r"__init__.py", "python-module", "Python modules use __init__.py marker", "structure"),
    (r"_render_.*\.py", "writer-prefix", "Writer helper functions use _render_ prefix", "naming"),
]

# Pattern signatures
_ERROR_HANDLER_PATTERNS: list[tuple[str, str, str, str]] = [
    ("emit_gate_failure", "gate-failure-emission", "Error handling uses emit_gate_failure pattern", "error-handling"),
    ("safe_log_error", "safe-error-logging", "Non-critical errors use safe_log_error", "error-handling"),
    ("install_global_handlers", "global-handler-install", "Global handlers installed at module init", "error-handling"),
]

_IMPORT_PATTERNS: list[tuple[str, str, str, str]] = [
    ("try:\n    from", "fallback-import", "Imports use try/except for optional dependencies", "import"),
    ("TYPE_CHECKING", "type-checking-import", "Type-only imports guarded by TYPE_CHECKING", "import"),
    ("from __future__ import annotations", "future-annotations", "Files use postponed evaluation of annotations", "import"),
]


# ---------------------------------------------------------------------------
# Discovery Functions
# ---------------------------------------------------------------------------


def _safe_list_dir(path: Path, max_items: int = 50) -> list[Path]:
    """List directory contents safely."""
    try:
        return list(path.iterdir())[:max_items]
    except (OSError, PermissionError):
        return []


def _file_exists(path: Path) -> bool:
    """Check if file exists safely."""
    try:
        return path.is_file()
    except (OSError, PermissionError):
        return False


def _read_first_lines(path: Path, max_lines: int = 100) -> list[str]:
    """Read first N lines of a file safely."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = []
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
            return lines
    except (OSError, PermissionError):
        return []


def _find_files_by_pattern(repo_root: Path, pattern: str, max_files: int = 20) -> list[Path]:
    """Find files matching a glob pattern (searches two levels deep)."""
    results: list[Path] = []
    try:
        # First check root level
        for entry in repo_root.iterdir():
            if entry.is_file() and entry.match(pattern):
                results.append(entry)
                if len(results) >= max_files:
                    return results
        
        # Then check one level deep (for files like governance_spec/phase_api.yaml)
        for entry in repo_root.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    for subentry in entry.iterdir():
                        if subentry.is_file() and subentry.match(pattern):
                            results.append(subentry)
                            if len(results) >= max_files:
                                return results
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return results


def discover_ssots(repo_root: Path) -> list[SSOTFact]:
    """Discover Sources of Single Truth.
    
    SSOTs are files/directories that serve as the authoritative source
    for specific concerns (phase routing, session state, binding paths, etc.)
    
    Conservative approach: Only report SSOTs with HIGH or MEDIUM confidence.
    """
    ssots: list[SSOTFact] = []
    
    # Check for known SSOT files
    for concern, patterns in _KNOWN_SSOTS.items():
        for filename, authority, schema in patterns:
            matches = _find_files_by_pattern(repo_root, filename)
            for match in matches[:2]:
                ssots.append(SSOTFact(
                    concern=concern,
                    path=str(match.relative_to(repo_root)),
                    authority=authority,
                    evidence=Evidence("file_exists", str(match), Confidence.HIGH),
                    schema=schema,
                ))
    
    # Special case: repo-policy in .opencode directory
    repo_policy_path = repo_root / ".opencode" / "governance-repo-policy.json"
    if _file_exists(repo_policy_path):
        ssots.append(SSOTFact(
            concern="repo-policy",
            path=str(repo_policy_path.relative_to(repo_root)),
            authority="repo-ssot",
            evidence=Evidence("file_exists", str(repo_policy_path), Confidence.HIGH),
            schema="opencode-governance-repo-policy.v1",
        ))
    
    return ssots


def discover_invariants(repo_root: Path) -> list[InvariantFact]:
    """Discover invariants — rules/conditions that must always be true.
    
    Invariants are detected by searching for specific patterns in code
    and configuration files. Conservative approach: Only report invariants
    with clear evidence.
    """
    invariants: list[InvariantFact] = []
    
    # Check for path constraint invariants
    config_root = repo_root / "governance.paths.json"
    if _file_exists(config_root):
        # If governance.paths.json exists, config-root-outside-repo is enforced
        invariants.append(InvariantFact(
            rule="Config root must be outside repository root",
            category="path-constraint",
            evidence=Evidence("file_exists", "governance.paths.json", Confidence.HIGH),
            enforcement="gate",
        ))
    
    # Check for fingerprint format invariant
    paths_json_content = _read_first_lines(config_root, 50)
    if any("fingerprint" in line.lower() for line in paths_json_content):
        invariants.append(InvariantFact(
            rule="Repository fingerprint must be 24-hex format",
            category="data-integrity",
            evidence=Evidence("pattern_match", "governance.paths.json", Confidence.MEDIUM),
            enforcement="validation",
        ))
    
    # Check for phase ordering invariant
    phase_api_files = _find_files_by_pattern(repo_root, "phase_api.*")
    if phase_api_files:
        invariants.append(InvariantFact(
            rule="Phase 1.3 (Rulebook Load) is mandatory before Phase 2+",
            category="phase-ordering",
            evidence=Evidence("file_exists", str(phase_api_files[0]), Confidence.HIGH),
            enforcement="gate",
        ))
    
    # Check for SESSION_STATE existence requirement
    session_files = _find_files_by_pattern(repo_root, "SESSION_STATE.json")
    if session_files:
        invariants.append(InvariantFact(
            rule="SESSION_STATE file must exist before persistence operations",
            category="data-integrity",
            evidence=Evidence("file_exists", str(session_files[0]), Confidence.HIGH),
            enforcement="gate",
        ))
    
    return invariants


def discover_conventions(repo_root: Path) -> list[ConventionFact]:
    """Discover conventions — established patterns and standards.
    
    Conventions are inferred from file naming, directory structure,
    and code patterns. Conservative approach: Only report conventions
    with clear evidence.
    """
    conventions: list[ConventionFact] = []
    
    # Check for test naming convention
    test_files = _find_files_by_pattern(repo_root / "tests" if (repo_root / "tests").is_dir() else repo_root, "test_*.py")
    if len(test_files) >= 3:  # Need multiple files to establish pattern
        conventions.append(ConventionFact(
            name="test-naming",
            description="Python test files use test_*.py naming convention",
            category="naming",
            evidence=Evidence("pattern_match", f"tests/: {len(test_files)} test files", Confidence.HIGH),
            scope="global",
        ))
    
    # Check for Python module convention
    init_files = _find_files_by_pattern(repo_root, "__init__.py")
    if len(init_files) >= 2:
        conventions.append(ConventionFact(
            name="python-module",
            description="Python packages use __init__.py module markers",
            category="structure",
            evidence=Evidence("pattern_match", f"{len(init_files)} __init__.py files", Confidence.HIGH),
            scope="global",
        ))
    
    # Check for markdown documentation convention
    md_files = _find_files_by_pattern(repo_root, "*.md")
    if len(md_files) >= 3:
        conventions.append(ConventionFact(
            name="markdown-docs",
            description="Documentation and specs use Markdown format",
            category="documentation",
            evidence=Evidence("pattern_match", f"{len(md_files)} .md files", Confidence.HIGH),
            scope="global",
        ))
    
    # Check for governance module naming convention
    gov_modules = [d for d in _safe_list_dir(repo_root) if d.is_dir() and d.name.startswith("governance_")]
    if len(gov_modules) >= 2:
        conventions.append(ConventionFact(
            name="governance-module-naming",
            description="Governance modules use governance_ prefix",
            category="naming",
            evidence=Evidence("pattern_match", f"{len(gov_modules)} governance_* dirs", Confidence.HIGH),
            scope="global",
        ))
    
    # Check for writer naming convention
    writer_files = _find_files_by_pattern(repo_root / "artifacts" / "writers" if (repo_root / "artifacts" / "writers").is_dir() else repo_root, "*.py")
    writer_count = sum(1 for f in writer_files if "writer" in str(f).lower() or "render" in str(f).lower())
    if writer_count >= 2 or len([f for f in _safe_list_dir(repo_root / "artifacts" / "writers" if (repo_root / "artifacts" / "writers").is_dir() else repo_root) if f.is_file() and f.suffix == ".py"]) >= 2:
        conventions.append(ConventionFact(
            name="writer-separation",
            description="Artifact writers are separated into dedicated modules under artifacts/writers/",
            category="structure",
            evidence=Evidence("directory_structure", "artifacts/writers/", Confidence.MEDIUM),
            scope="global",
        ))
    
    return conventions


def discover_patterns(repo_root: Path) -> list[PatternFact]:
    """Discover recurring patterns in the codebase.
    
    Patterns are detected by searching for specific code signatures
    across Python files. Conservative approach: Only report patterns
    with multiple occurrences.
    """
    patterns: list[PatternFact] = []
    
    # Collect Python files for pattern scanning
    python_files: list[Path] = []
    for entry in _safe_list_dir(repo_root):
        if entry.is_file() and entry.suffix == ".py":
            python_files.append(entry)
        elif entry.is_dir() and not entry.name.startswith(".") and entry.name != "__pycache__":
            for subentry in _safe_list_dir(entry):
                if subentry.is_file() and subentry.suffix == ".py":
                    python_files.append(subentry)
    
    # Scan for error handling patterns
    error_pattern_locations: dict[str, list[str]] = {"emit_gate_failure": [], "safe_log_error": [], "install_global_handlers": []}
    for py_file in python_files[:30]:  # Limit scanning
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(py_file.relative_to(repo_root))
            for pattern_name in error_pattern_locations:
                if pattern_name in content:
                    error_pattern_locations[pattern_name].append(rel_path)
        except Exception:
            pass
    
    for pattern_name, locations in error_pattern_locations.items():
        if len(locations) >= 2:
            pattern_info = next((p for p in _ERROR_HANDLER_PATTERNS if p[0] == pattern_name), None)
            if pattern_info:
                _, pattern_id, description, category = pattern_info
                patterns.append(PatternFact(
                    name=pattern_id,
                    description=description,
                    locations=locations[:5],  # Limit locations
                    category=category,
                    evidence=Evidence("pattern_match", f"{len(locations)} occurrences", Confidence.HIGH),
                ))
    
    # Scan for import patterns
    import_pattern_locations: dict[str, list[str]] = {"fallback-import": [], "type-checking-import": [], "future-annotations": []}
    for py_file in python_files[:30]:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(py_file.relative_to(repo_root))
            if "try:\n    from" in content or "try:\n        from" in content:
                import_pattern_locations["fallback-import"].append(rel_path)
            if "TYPE_CHECKING" in content:
                import_pattern_locations["type-checking-import"].append(rel_path)
            if "from __future__ import annotations" in content:
                import_pattern_locations["future-annotations"].append(rel_path)
        except Exception:
            pass
    
    for pattern_name, locations in import_pattern_locations.items():
        if len(locations) >= 2:
            _, pattern_id, description, category = next(
                (p for p in _IMPORT_PATTERNS if p[1] == pattern_name),
                (None, pattern_name, f"Import pattern: {pattern_name}", "import")
            )
            patterns.append(PatternFact(
                name=pattern_id,
                description=description,
                locations=locations[:5],
                category=category,
                evidence=Evidence("pattern_match", f"{len(locations)} occurrences", Confidence.HIGH),
            ))
    
    return patterns


def discover_defaults(repo_root: Path) -> list[DefaultFact]:
    """Discover default values and fallback behaviors.
    
    Defaults are inferred from code defaults and configuration patterns.
    """
    defaults: list[DefaultFact] = []
    
    # Check for default profile
    policy_files = _find_files_by_pattern(repo_root / ".opencode" if (repo_root / ".opencode").is_dir() else repo_root, "governance-repo-policy.json")
    if policy_files:
        try:
            content = policy_files[0].read_text(encoding="utf-8")
            if "solo" in content.lower():
                defaults.append(DefaultFact(
                    setting="operating-mode",
                    value="solo",
                    evidence=Evidence("file_content", str(policy_files[0]), Confidence.MEDIUM),
                    override_path=str(policy_files[0]),
                ))
        except Exception:
            pass
    
    # Default fingerprint format
    defaults.append(DefaultFact(
        setting="fingerprint-format",
        value="24-hex",
        evidence=Evidence("convention", "governance_runtime", Confidence.HIGH),
    ))
    
    # Default config root
    defaults.append(DefaultFact(
        setting="config-root",
        value="~/.config/opencode",
        evidence=Evidence("convention", "governance_runtime/paths.py", Confidence.HIGH),
    ))
    
    return defaults


def discover_deviations(repo_root: Path) -> list[DeviationFact]:
    """Discover deviations from expected norms.
    
    Deviations are potential issues or inconsistencies found during discovery.
    Conservative: Only report clear deviations with evidence.
    """
    deviations: list[DeviationFact] = []
    
    # Check for missing tests directory
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        deviations.append(DeviationFact(
            description="No tests/ directory found",
            expected="tests/ directory with test suites",
            observed="No tests directory",
            severity="info",
            evidence=Evidence("directory_missing", "tests/", Confidence.HIGH),
            recommendation="Consider adding a tests/ directory for test organization",
        ))
    
    # Check for missing CI configuration
    ci_dirs = [d for d in _safe_list_dir(repo_root) if d.name == ".github" or d.name == ".gitlab-ci.yml"]
    if not ci_dirs and not (repo_root / ".github").is_dir():
        pass  # Not all repos have CI, this is just informational
    
    return deviations


def discover_semantic_facts(
    repo_root: Path,
    *,
    profile: str = "",
    repo_fingerprint: str = "",
) -> SemanticFacts:
    """Run all semantic discovery and return facts.
    
    This is the main entry point for semantic discovery.
    Conservative approach: Only report facts with clear evidence.
    
    Args:
        repo_root: Root directory of the repository
        profile: Operating profile (solo/team/regulated)
        repo_fingerprint: Repository fingerprint
    
    Returns:
        SemanticFacts with all discovered semantic information
    """
    from datetime import datetime, timezone
    
    discovered_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    # Run all discovery functions
    ssots = discover_ssots(repo_root)
    invariants = discover_invariants(repo_root)
    conventions = discover_conventions(repo_root)
    patterns = discover_patterns(repo_root)
    defaults = discover_defaults(repo_root)
    deviations = discover_deviations(repo_root)
    
    return SemanticFacts(
        ssots=ssots,
        invariants=invariants,
        conventions=conventions,
        patterns=patterns,
        defaults=defaults,
        deviations=deviations,
        discovered_at=discovered_at,
    )


# ---------------------------------------------------------------------------
# Rendering Helpers for Workspace Memory
# ---------------------------------------------------------------------------


def render_conventions_yaml(conventions: list[ConventionFact]) -> str:
    """Render conventions as YAML mapping for workspace-memory.yaml."""
    if not conventions:
        return "{}"
    parts = []
    for c in conventions[:10]:
        parts.append(f'    {c.name}: "{c.description[:80]}"')
    return "{\n" + "\n".join(parts) + "\n  }"


def render_patterns_yaml(patterns: list[PatternFact]) -> str:
    """Render patterns as YAML mapping for workspace-memory.yaml."""
    if not patterns:
        return "{}"
    parts = []
    for p in patterns[:10]:
        parts.append(f'    {p.name}: "{p.description[:80]}"')
    return "{\n" + "\n".join(parts) + "\n  }"


def render_defaults_yaml(defaults: list[DefaultFact]) -> str:
    """Render defaults as YAML mapping for workspace-memory.yaml."""
    if not defaults:
        return "{}"
    parts = []
    for d in defaults[:10]:
        parts.append(f'    {d.setting}: "{d.value}"')
    return "{\n" + "\n".join(parts) + "\n  }"


def render_deviations_yaml(deviations: list[DeviationFact]) -> str:
    """Render deviations as YAML list for workspace-memory.yaml."""
    if not deviations:
        return "[]"
    parts = []
    for d in deviations[:5]:
        parts.append(f'    - description: "{d.description[:60]}"')
        parts.append(f'      severity: "{d.severity}"')
    return "[\n" + "\n".join(parts) + "\n  ]"


def render_ssots_summary(ssots: list[SSOTFact]) -> list[str]:
    """Render SSOTs as markdown bullet list."""
    lines = []
    for s in ssots[:10]:
        lines.append(f"- **{s.concern}**: `{s.path}` ({s.authority})")
    return lines


def render_invariants_summary(invariants: list[InvariantFact]) -> list[str]:
    """Render invariants as markdown bullet list."""
    lines = []
    for i in invariants[:10]:
        enforcement = f" [{i.enforcement}]" if i.enforcement else ""
        lines.append(f"- {i.rule}{enforcement}")
    return lines
