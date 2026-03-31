#!/usr/bin/env python3
"""Repo cache writer — renders repo-cache.yaml from discovery facts.

This module renders the machine-readable repo cache index from
StructuralFacts discovered by deep_repo_discovery.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from governance_runtime.infrastructure.repo_discovery import (
        BuildAndToolingFact,
        DataStoreFact,
        EntryPointFact,
        ModuleFact,
        StructuralFacts,
        TestingFact,
    )


def render_repo_cache(
    *,
    date: str,
    repo_name: str,
    profile: str,
    profile_evidence: str,
    discovery: StructuralFacts,
) -> str:
    """Render repo cache from structural discovery facts.

    Args:
        date: ISO date string
        repo_name: Repository name
        profile: Operating profile (solo/team/regulated)
        profile_evidence: Evidence for profile detection
        discovery: StructuralFacts from deep discovery

    Returns:
        YAML-formatted repo cache content
    """
    # Import here to avoid circular imports
    from governance_runtime.infrastructure.repo_discovery import (
        Confidence,
    )

    # Render modules
    modules_yaml = _render_modules(discovery.modules)

    # Render entry points
    entry_points_yaml = _render_entry_points(discovery.entry_points)

    # Render data stores
    data_stores_yaml = _render_data_stores(discovery.data_stores)

    # Render testing surface
    testing_yaml = _render_testing(discovery.testing_surface)

    # Build architecture summary from core subsystems
    architecture = ", ".join(discovery.core_subsystems) if discovery.core_subsystems else "discovery incomplete"

    # Build and tooling
    build_yaml = _render_build(discovery.build_and_tooling)

    lines = [
        "RepoCache:",
        '  Version: "2.0"',
        f'  LastUpdated: "{date}"',
        f'  RepoName: "{repo_name}"',
        f'  GitHead: "discovered"',
        f'  RepoSignature: "discovered"',
        f'  ProfileDetected: "{profile}"',
        f'  ProfileEvidence: "{profile_evidence}"',
        "  RepoMapDigest:",
        f'    RepositoryType: "{discovery.repository_type}"',
        f'    Architecture: "{architecture}"',
        f"    Modules: [{modules_yaml}]",
        f"    EntryPoints: [{entry_points_yaml}]",
        f"    DataStores: [{data_stores_yaml}]",
        f"    Testing: [{testing_yaml}]",
        "  ConventionsDigest:",
        '    - "Discovery-based snapshot (v2.0)"',
        f"  BuildAndTooling: {build_yaml}",
        "  CacheHashChecks: []",
        "  InvalidateOn:",
        '    - "Profile change"',
        '    - "Rulebook update"',
        '    - "Repository structure change"',
        "",
    ]

    return "\n".join(lines)


def _render_modules(modules: list[ModuleFact]) -> str:
    """Render modules as YAML list."""
    if not modules:
        return ""
    parts = []
    for m in modules[:20]:  # Performance limit
        name = m.name.replace('"', '\\"')
        path = m.path.replace('"', '\\"')
        parts.append(f'{{name: "{name}", path: "{path}"}}')
    return ", ".join(parts)


def _render_entry_points(entry_points: list[EntryPointFact]) -> str:
    """Render entry points as YAML list."""
    if not entry_points:
        return ""
    parts = []
    for ep in entry_points[:20]:
        kind = ep.kind.replace('"', '\\"')
        path = ep.path.replace('"', '\\"')
        parts.append(f'{{kind: "{kind}", path: "{path}"}}')
    return ", ".join(parts)


def _render_data_stores(stores: list[DataStoreFact]) -> str:
    """Render data stores as YAML list."""
    if not stores:
        return ""
    parts = []
    for s in stores[:20]:
        kind = s.kind.replace('"', '\\"')
        path = s.path.replace('"', '\\"')
        schema = s.schema_hint.replace('"', '\\"')
        parts.append(f'{{kind: "{kind}", path: "{path}", schema: "{schema}"}}')
    return ", ".join(parts)


def _render_testing(tests: list[TestingFact]) -> str:
    """Render testing surface as YAML list."""
    if not tests:
        return ""
    parts = []
    for t in tests[:20]:
        suite = t.suite.replace('"', '\\"')
        path = t.path.replace('"', '\\"')
        scope = t.scope.replace('"', '\\"')
        parts.append(f'{{suite: "{suite}", path: "{path}", scope: "{scope}"}}')
    return ", ".join(parts)


def _render_build(build: BuildAndToolingFact) -> str:
    """Render build and tooling as YAML dict."""
    pm = build.package_manager or "unknown"
    pm = pm.replace('"', '\\"')

    parts = [f'package_manager: "{pm}"']

    if build.ci_commands:
        ci_items = [f'"{c.replace(chr(34), chr(39))}"' for c in build.ci_commands[:10]]
        parts.append(f"ci_commands: [{', '.join(ci_items)}]")

    if build.scripts:
        script_items = [f'"{s.replace(chr(34), chr(39))}"' for s in build.scripts[:10]]
        parts.append(f"scripts: [{', '.join(script_items)}]")

    return "{ " + ", ".join(parts) + " }"


# ---------------------------------------------------------------------------
# Legacy compatibility wrapper
# ---------------------------------------------------------------------------


def render_repo_cache_legacy(
    *,
    date: str,
    repo_name: str,
    profile: str,
    profile_evidence: str,
    repository_type: str,
) -> str:
    """Legacy wrapper for backward compatibility.

    Creates a minimal StructuralFacts from repository_type string
    and delegates to the new implementation.
    """
    # Import here to avoid circular imports at module level
    from governance_runtime.infrastructure.repo_discovery import (
        BuildAndToolingFact,
        Confidence,
        Evidence,
        StructuralFacts,
    )

    minimal_facts = StructuralFacts(
        repository_type=repository_type,
        layers=[],
        core_subsystems=[],
        modules=[],
        entry_points=[],
        data_stores=[],
        build_and_tooling=BuildAndToolingFact(
            package_manager=None,
            ci_commands=[],
            scripts=[],
            evidence=Evidence("legacy", "compatibility", Confidence.LOW),
        ),
        testing_surface=[],
        discovered_at=date,
    )

    return render_repo_cache(
        date=date,
        repo_name=repo_name,
        profile=profile,
        profile_evidence=profile_evidence,
        discovery=minimal_facts,
    )
