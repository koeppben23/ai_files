#!/usr/bin/env python3
"""Deep Repository Discovery — structural facts for artifact generation.

Pass 1: Structural Discovery (deterministic, filesystem-based)

This module provides structured discovery of repository topology, modules,
entry points, data stores, build tooling, and testing surface. The discovery
is designed to be:
- Fast: Uses targeted file system scans, not recursive deep scans
- Deterministic: Same repo always produces same facts
- Evidence-based: Every fact has source and confidence level

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from governance_runtime.infrastructure.repo_discovery.semantic_discovery import SemanticFacts

# ---------------------------------------------------------------------------
# Fact Types with Confidence/Evidence
# ---------------------------------------------------------------------------


class Confidence(Enum):
    """Confidence level for discovered facts."""
    HIGH = "high"      # Direct filesystem evidence, file exists
    MEDIUM = "medium"  # Structural inference, pattern match
    LOW = "low"        # Heuristic, incomplete evidence


@dataclass(frozen=True)
class Evidence:
    """Evidence supporting a discovered fact."""
    source: str        # "file_exists", "pattern_match", "convention", "git"
    reference: str     # Path or identifier of evidence source
    confidence: Confidence

    def with_confidence(self, confidence: Confidence) -> Evidence:
        """Return new evidence with specified confidence level."""
        return Evidence(self.source, self.reference, confidence)


@dataclass(frozen=True)
class ModuleFact:
    """Discovered module with responsibility."""
    name: str
    path: str
    responsibility: str
    evidence: Evidence


@dataclass(frozen=True)
class EntryPointFact:
    """Discovered entry point."""
    kind: str           # "bootstrap", "plugin", "cli", "runtime", "command"
    path: str
    purpose: str
    evidence: Evidence


@dataclass(frozen=True)
class DataStoreFact:
    """Discovered data store or state file."""
    kind: str           # "session_state", "workspace_artifact", "config", "spec"
    path: str
    schema_hint: str    # "json", "yaml", "md", "unknown"
    evidence: Evidence


@dataclass(frozen=True)
class TestingFact:
    """Discovered test suite."""
    suite: str
    path: str
    scope: str          # "unit", "integration", "e2e", "conformance"
    evidence: Evidence


@dataclass(frozen=True)
class BuildAndToolingFact:
    """Discovered build and tooling configuration."""
    package_manager: str | None   # "pip", "npm", "yarn", "poetry", etc.
    ci_commands: list[str]
    scripts: list[str]
    evidence: Evidence


@dataclass(frozen=True)
class StructuralFacts:
    """Complete structural discovery results.
    
    Contains only filesystem-observable facts: topology, modules,
    entry points, data stores, build tooling, testing surface.
    """
    repository_type: str          # "monorepo" | "single-package" | "library" | "app"
    layers: list[str]
    core_subsystems: list[str]
    modules: list[ModuleFact]
    entry_points: list[EntryPointFact]
    data_stores: list[DataStoreFact]
    build_and_tooling: BuildAndToolingFact
    testing_surface: list[TestingFact]
    discovered_at: str
    discovery_version: str = "2.0"


@dataclass(frozen=True)
class DiscoveredFacts:
    """Combined discovery results: structural + semantic.

    This is the canonical container for all repository facts.
    Structural facts are deterministic; semantic facts are interpretive.
    """
    structural: StructuralFacts
    semantic: SemanticFacts | None = None


# ---------------------------------------------------------------------------
# Constants for Performance
# ---------------------------------------------------------------------------

# Known governance module paths (high confidence recognition)
_GOVERNANCE_MODULES = {
    "governance_runtime": "Core governance runtime (kernel, application, infrastructure)",
    "governance_content": "Operator docs and command rails",
    "governance_spec": "Policy and spec source of truth",
}

# Entry point patterns (fast regex, no deep scanning)
_ENTRY_POINT_PATTERNS = [
    (re.compile(r"opencode-governance-bootstrap(\.cmd)?$"), "bootstrap"),
    (re.compile(r"\.mjs$"), "plugin"),
    (re.compile(r"^cli\.py$"), "cli"),
]

# Data store file patterns
_DATA_STORE_PATTERNS = [
    (re.compile(r"SESSION_STATE\.json$"), "session_state", "json"),
    (re.compile(r"-pointer\.json$"), "pointer", "json"),
    (re.compile(r"\.yaml$"), "artifact", "yaml"),
    (re.compile(r"\.yml$"), "artifact", "yaml"),
    (re.compile(r"\.md$"), "documentation", "md"),
]

# Test directory patterns
_TEST_PATTERNS = [
    (re.compile(r"^tests?[/\\]unit"), "unit"),
    (re.compile(r"^tests?[/\\]integration"), "integration"),
    (re.compile(r"^tests?[/\\]e2e"), "e2e"),
    (re.compile(r"^tests?[/\\]conformance"), "conformance"),
]

# Performance limit: max files to scan per directory
_MAX_FILES_PER_DIR = 200
_MAX_DEPTH = 4


# ---------------------------------------------------------------------------
# Utility Functions (Performance-Optimized)
# ---------------------------------------------------------------------------


def _safe_list_dir(path: Path, max_items: int = _MAX_FILES_PER_DIR) -> list[Path]:
    """List directory contents with performance guard."""
    try:
        entries = list(path.iterdir())[:max_items]
        return entries
    except (OSError, PermissionError):
        return []


def _file_exists(path: Path) -> bool:
    """Check if file exists, returns False on any error."""
    try:
        return path.is_file()
    except (OSError, PermissionError):
        return False


def _read_first_lines(path: Path, max_lines: int = 50) -> list[str]:
    """Read first N lines of a file efficiently."""
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


def _get_git_head(repo_root: Path) -> str:
    """Get current git HEAD commit hash (short)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Structural Discovery Functions
# ---------------------------------------------------------------------------


def discover_topology(repo_root: Path) -> tuple[str, list[str], list[str]]:
    """Discover repository topology.

    Returns:
        (repository_type, layers, core_subsystems)
    """
    repo_root_str = str(repo_root)

    # Check for monorepo indicators
    has_multiple_packages = False
    layers = []
    core_subsystems = []

    entries = _safe_list_dir(repo_root)

    # Identify layers (top-level directories that look like governance)
    for entry in entries:
        if entry.is_dir():
            name = entry.name
            if name.startswith("governance_"):
                layers.append(name)
                if name in _GOVERNANCE_MODULES:
                    core_subsystems.append(name)
            elif name in ("bin", "commands", "plugins", "workspaces"):
                layers.append(name)

    # Determine repository type
    # Check for package.json or pyproject.toml at root
    has_package_json = _file_exists(repo_root / "package.json")
    has_pyproject = _file_exists(repo_root / "pyproject.toml")
    has_setup_py = _file_exists(repo_root / "setup.py")

    if len(layers) > 2:
        repository_type = "monorepo"
    elif has_package_json and has_pyproject:
        repository_type = "monorepo"
    elif has_pyproject or has_setup_py:
        # Check if it's a library or app
        pyproject_content = _read_first_lines(repo_root / "pyproject.toml" if has_pyproject else repo_root / "setup.py", 20)
        content_str = "".join(pyproject_content).lower()
        if "library" in content_str or "packages" in content_str:
            repository_type = "library"
        else:
            repository_type = "app"
    elif has_package_json:
        repository_type = "app"
    else:
        repository_type = "single-package"

    return repository_type, layers, core_subsystems


def discover_modules(repo_root: Path) -> list[ModuleFact]:
    """Discover Python/JS modules with responsibilities.

    Performance: Scans only top-level directories, not recursive.
    """
    modules: list[ModuleFact] = []
    entries = _safe_list_dir(repo_root)

    for entry in entries:
        if not entry.is_dir():
            continue

        name = entry.name

        # Skip hidden directories and common non-module directories
        if name.startswith(".") or name in ("__pycache__", "node_modules", ".git"):
            continue

        # Check for Python module indicators
        has_init = _file_exists(entry / "__init__.py")
        has_py_files = any(e.suffix == ".py" for e in _safe_list_dir(entry)[:10] if e.is_file())

        # Check for JS/TS module indicators
        has_index_js = _file_exists(entry / "index.js")
        has_index_ts = _file_exists(entry / "index.ts")

        if has_init or has_py_files or has_index_js or has_index_ts:
            # Get responsibility from known modules or README
            responsibility = _GOVERNANCE_MODULES.get(name, "")
            if not responsibility:
                readme_path = entry / "README.md"
                if _file_exists(readme_path):
                    readme_lines = _read_first_lines(readme_path, 10)
                    responsibility = " ".join(readme_lines).strip()[:100]
                else:
                    responsibility = f"{name} module"

            modules.append(ModuleFact(
                name=name,
                path=str(entry.relative_to(repo_root)),
                responsibility=responsibility,
                evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
            ))

    return modules


def discover_entry_points(repo_root: Path) -> list[EntryPointFact]:
    """Discover bootstrap, plugins, CLI, runtime entry points.

    Performance: Scans bin/ and top-level, no recursive deep scan.
    """
    entry_points: list[EntryPointFact] = []

    # Check bin/ directory
    bin_dir = repo_root / "bin"
    if bin_dir.is_dir():
        for entry in _safe_list_dir(bin_dir):
            if entry.is_file():
                kind = "bootstrap"
                purpose = entry.name
                for pattern, detected_kind in _ENTRY_POINT_PATTERNS:
                    if pattern.search(entry.name):
                        kind = detected_kind
                        break
                entry_points.append(EntryPointFact(
                    kind=kind,
                    path=str(entry.relative_to(repo_root)),
                    purpose=f"{kind}: {entry.name}",
                    evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
                ))

    # Check for plugins
    plugins_dir = repo_root / "plugins"
    if plugins_dir.is_dir():
        for entry in _safe_list_dir(plugins_dir):
            if entry.is_file() and entry.suffix in (".mjs", ".js"):
                entry_points.append(EntryPointFact(
                    kind="plugin",
                    path=str(entry.relative_to(repo_root)),
                    purpose=f"plugin: {entry.name}",
                    evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
                ))

    # Check commands/ directory for command entry points
    commands_dir = repo_root / "commands"
    if commands_dir.is_dir():
        for entry in _safe_list_dir(commands_dir):
            if entry.is_file() and entry.suffix == ".md":
                entry_points.append(EntryPointFact(
                    kind="command",
                    path=str(entry.relative_to(repo_root)),
                    purpose=f"command rail: {entry.stem}",
                    evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
                ))

    # Check for CLI entry points at root
    for entry in _safe_list_dir(repo_root):
        if entry.is_file() and entry.name in ("cli.py", "main.py", "run.py"):
            entry_points.append(EntryPointFact(
                kind="cli",
                path=str(entry.relative_to(repo_root)),
                purpose=f"CLI entry: {entry.name}",
                evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
            ))

    return entry_points


def discover_data_stores(repo_root: Path) -> list[DataStoreFact]:
    """Discover session state, workspace artifacts, config, spec files.

    Performance: Only checks known locations, no recursive scan.
    """
    data_stores: list[DataStoreFact] = []

    # Check for session state files in workspaces
    workspaces_dir = repo_root / "workspaces"
    if workspaces_dir.is_dir():
        for ws_entry in _safe_list_dir(workspaces_dir):
            if ws_entry.is_dir():
                session_file = ws_entry / "SESSION_STATE.json"
                if _file_exists(session_file):
                    data_stores.append(DataStoreFact(
                        kind="session_state",
                        path=str(session_file.relative_to(repo_root)),
                        schema_hint="json",
                        evidence=Evidence("file_exists", str(session_file), Confidence.HIGH),
                    ))

    # Check for governance spec files
    spec_dir = repo_root / "governance_spec"
    if spec_dir.is_dir():
        for entry in _safe_list_dir(spec_dir):
            if entry.is_file() and entry.suffix in (".yaml", ".yml"):
                data_stores.append(DataStoreFact(
                    kind="spec",
                    path=str(entry.relative_to(repo_root)),
                    schema_hint="yaml",
                    evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
                ))

    # Check for pointer files
    for entry in _safe_list_dir(repo_root):
        if entry.is_file() and "pointer" in entry.name.lower() and entry.suffix == ".json":
            data_stores.append(DataStoreFact(
                kind="pointer",
                path=str(entry.relative_to(repo_root)),
                schema_hint="json",
                evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
            ))

    # Check for config files
    config_files = ("opencode.json", "governance.paths.json", "governance-config.json")
    for config_name in config_files:
        config_path = repo_root / config_name
        if _file_exists(config_path):
            data_stores.append(DataStoreFact(
                kind="config",
                path=str(config_path.relative_to(repo_root)),
                schema_hint="json" if config_path.suffix == ".json" else "yaml",
                evidence=Evidence("file_exists", str(config_path), Confidence.HIGH),
            ))

    return data_stores


def discover_build_and_tooling(repo_root: Path) -> BuildAndToolingFact:
    """Discover package manager, CI commands, scripts.

    Performance: Only checks known config files, no deep parsing.
    """
    package_manager: str | None = None
    ci_commands: list[str] = []
    scripts: list[str] = []

    # Detect package manager
    if _file_exists(repo_root / "pyproject.toml"):
        package_manager = "pip/pyproject"
    elif _file_exists(repo_root / "package.json"):
        package_manager = "npm"
    elif _file_exists(repo_root / "yarn.lock"):
        package_manager = "yarn"
    elif _file_exists(repo_root / "Cargo.toml"):
        package_manager = "cargo"

    # Check for CI commands
    gh_workflows = repo_root / ".github" / "workflows"
    if gh_workflows.is_dir():
        ci_commands.append("github-actions")
        for entry in _safe_list_dir(gh_workflows):
            if entry.is_file() and entry.suffix in (".yml", ".yaml"):
                ci_commands.append(f"github-actions:{entry.stem}")

    # Check for Makefile
    if _file_exists(repo_root / "Makefile"):
        ci_commands.append("make")

    # Check for common scripts
    script_files = ("install.sh", "install.ps1", "smoketest.sh")
    for script_name in script_files:
        if _file_exists(repo_root / script_name):
            scripts.append(script_name)
        # Also check in install/ directory
        install_script = repo_root / "install" / script_name
        if _file_exists(install_script):
            scripts.append(f"install/{script_name}")

    return BuildAndToolingFact(
        package_manager=package_manager,
        ci_commands=ci_commands,
        scripts=scripts,
        evidence=Evidence("file_exists", str(repo_root), Confidence.HIGH),
    )


def discover_testing_surface(repo_root: Path) -> list[TestingFact]:
    """Discover test suites and their scope.

    Performance: Scans tests/ directory at top level only.
    """
    testing_surface: list[TestingFact] = []

    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return testing_surface

    # Count test files in tests/ subdirectories
    for entry in _safe_list_dir(tests_dir):
        if entry.is_dir():
            scope = "unit"
            for pattern, detected_scope in _TEST_PATTERNS:
                if pattern.search(str(entry)):
                    scope = detected_scope
                    break

            # Count test files
            test_files = [f for f in _safe_list_dir(entry) if f.suffix == ".py" and f.name.startswith("test_")]
            if test_files:
                testing_surface.append(TestingFact(
                    suite=entry.name,
                    path=str(entry.relative_to(repo_root)),
                    scope=scope,
                    evidence=Evidence("file_exists", str(entry), Confidence.HIGH),
                ))

    # Check for pytest config
    pytest_ini = repo_root / "pytest.ini"
    pyproject_test = repo_root / "pyproject.toml"
    if _file_exists(pytest_ini) or _file_exists(pyproject_test):
        testing_surface.append(TestingFact(
            suite="pytest-config",
            path="pytest.ini" if _file_exists(pytest_ini) else "pyproject.toml",
            scope="config",
            evidence=Evidence("file_exists", "pytest-config", Confidence.HIGH),
        ))

    return testing_surface


# ---------------------------------------------------------------------------
# Composition: Full Structural Discovery
# ---------------------------------------------------------------------------


def discover_structural_facts(
    repo_root: Path,
    *,
    profile: str = "",
    repo_fingerprint: str = "",
) -> StructuralFacts:
    """Run all structural discovery and return facts.

    This is the main entry point for structural discovery.
    Performance target: < 100ms for typical repositories.

    Args:
        repo_root: Root directory of the repository
        profile: Operating profile (solo/team/regulated)
        repo_fingerprint: Repository fingerprint

    Returns:
        StructuralFacts with all discovered information
    """
    discovered_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Run all discovery functions
    repository_type, layers, core_subsystems = discover_topology(repo_root)
    modules = discover_modules(repo_root)
    entry_points = discover_entry_points(repo_root)
    data_stores = discover_data_stores(repo_root)
    build_and_tooling = discover_build_and_tooling(repo_root)
    testing_surface = discover_testing_surface(repo_root)

    return StructuralFacts(
        repository_type=repository_type,
        layers=layers,
        core_subsystems=core_subsystems,
        modules=modules,
        entry_points=entry_points,
        data_stores=data_stores,
        build_and_tooling=build_and_tooling,
        testing_surface=testing_surface,
        discovered_at=discovered_at,
    )


# ---------------------------------------------------------------------------
# Rendering Helpers for Writers
# ---------------------------------------------------------------------------


def render_modules_yaml(modules: list[ModuleFact]) -> str:
    """Render modules as YAML list."""
    if not modules:
        return ""
    parts = []
    for m in modules[:20]:  # Performance limit
        parts.append(f'{{name: "{m.name}", path: "{m.path}", responsibility: "{m.responsibility[:50]}"}}')
    return ", ".join(parts)


def render_modules_md(modules: list[ModuleFact]) -> str:
    """Render modules as Markdown list."""
    if not modules:
        return "- (discovery incomplete)"
    lines = []
    for m in modules[:20]:
        lines.append(f"- **{m.name}** (`{m.path}`): {m.responsibility[:80]}")
    return "\n".join(lines)


def render_entry_points_yaml(entry_points: list[EntryPointFact]) -> str:
    """Render entry points as YAML list."""
    if not entry_points:
        return ""
    parts = []
    for ep in entry_points[:20]:
        parts.append(f'{{kind: "{ep.kind}", path: "{ep.path}"}}')
    return ", ".join(parts)


def render_entry_points_md(entry_points: list[EntryPointFact]) -> str:
    """Render entry points as Markdown list."""
    if not entry_points:
        return "- (discovery incomplete)"
    lines = []
    for ep in entry_points[:20]:
        lines.append(f"- **{ep.kind}**: `{ep.path}` — {ep.purpose[:60]}")
    return "\n".join(lines)


def render_data_stores_yaml(stores: list[DataStoreFact]) -> str:
    """Render data stores as YAML list."""
    if not stores:
        return ""
    parts = []
    for s in stores[:20]:
        parts.append(f'{{kind: "{s.kind}", path: "{s.path}", schema: "{s.schema_hint}"}}')
    return ", ".join(parts)


def render_data_stores_md(stores: list[DataStoreFact]) -> str:
    """Render data stores as Markdown list."""
    if not stores:
        return "- (discovery incomplete)"
    lines = []
    for s in stores[:20]:
        lines.append(f"- **{s.kind}**: `{s.path}` ({s.schema_hint})")
    return "\n".join(lines)


def render_testing_md(tests: list[TestingFact]) -> str:
    """Render testing surface as Markdown list."""
    if not tests:
        return "- (no test suites discovered)"
    lines = []
    for t in tests[:20]:
        lines.append(f"- **{t.suite}** (`{t.path}`): {t.scope}")
    return "\n".join(lines)


def render_build_yaml(build: BuildAndToolingFact) -> str:
    """Render build and tooling as YAML dict."""
    parts = [f'package_manager: "{build.package_manager or "unknown"}"']
    if build.ci_commands:
        ci_str = ", ".join(f'"{c}"' for c in build.ci_commands[:10])
        parts.append(f"ci_commands: [{ci_str}]")
    if build.scripts:
        scripts_str = ", ".join(f'"{s}"' for s in build.scripts[:10])
        parts.append(f"scripts: [{scripts_str}]")
    return "{ " + ", ".join(parts) + " }"


def render_build_md(build: BuildAndToolingFact) -> str:
    """Render build and tooling as Markdown."""
    lines = []
    lines.append(f"- Package manager: {build.package_manager or 'unknown'}")
    if build.ci_commands:
        lines.append(f"- CI: {', '.join(build.ci_commands[:5])}")
    if build.scripts:
        lines.append(f"- Scripts: {', '.join(build.scripts[:5])}")
    return "\n".join(lines) if lines else "- (discovery incomplete)"
