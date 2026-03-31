#!/usr/bin/env python3
"""Repo map digest writer — renders repo-map-digest.md from discovery facts.

This module renders the human-readable architecture report from
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


def repo_map_digest_section(date: str, discovery: StructuralFacts) -> str:
    """Render the Repo Map Digest section from structural facts.

    Args:
        date: ISO date string
        discovery: StructuralFacts from deep discovery

    Returns:
        Markdown-formatted digest section
    """
    # Build architecture from core subsystems
    architecture = ", ".join(discovery.core_subsystems) if discovery.core_subsystems else "discovery incomplete"

    # Build layers string
    layers_str = ", ".join(discovery.layers) if discovery.layers else "none"

    # Render modules
    modules_md = _render_modules_md(discovery.modules)

    # Render entry points
    entry_points_md = _render_entry_points_md(discovery.entry_points)

    # Render data stores
    data_stores_md = _render_data_stores_md(discovery.data_stores)

    # Render build and tooling
    build_md = _render_build_md(discovery.build_and_tooling)

    # Render testing surface
    testing_md = _render_testing_md(discovery.testing_surface)

    lines = [
        f"## Repo Map Digest — {date}",
        "Meta:",
        f"- RepositoryType: {discovery.repository_type}",
        f"- Layers: {layers_str}",
        f"- Provenance: Phase2-Discovery",
        "",
        f"RepositoryType: {discovery.repository_type}",
        f"Architecture: {architecture}",
        "Modules:",
        modules_md,
        "EntryPoints:",
        entry_points_md,
        "DataStores:",
        data_stores_md,
        "BuildAndTooling:",
        build_md,
        "Testing:",
        testing_md,
        "",
    ]

    return "\n".join(lines)


def render_repo_map_digest_create(
    *,
    date: str,
    repo_name: str,
    discovery: StructuralFacts,
) -> str:
    """Render complete repo map digest document.

    Args:
        date: ISO date string
        repo_name: Repository name
        discovery: StructuralFacts from deep discovery

    Returns:
        Complete Markdown document for repo-map-digest.md
    """
    section = repo_map_digest_section(date, discovery)
    return f"# Repo Map Digest\nRepo: {repo_name}\nLastUpdated: {date}\n\n{section}"


def _render_modules_md(modules: list[ModuleFact]) -> str:
    """Render modules as Markdown list."""
    if not modules:
        return "- (discovery incomplete)"
    lines = []
    for m in modules[:20]:
        resp = m.responsibility[:80] if m.responsibility else "module"
        lines.append(f"- **{m.name}** (`{m.path}`): {resp}")
    return "\n".join(lines)


def _render_entry_points_md(entry_points: list[EntryPointFact]) -> str:
    """Render entry points as Markdown list."""
    if not entry_points:
        return "- (discovery incomplete)"
    lines = []
    for ep in entry_points[:20]:
        purpose = ep.purpose[:60] if ep.purpose else ep.kind
        lines.append(f"- **{ep.kind}**: `{ep.path}` — {purpose}")
    return "\n".join(lines)


def _render_data_stores_md(stores: list[DataStoreFact]) -> str:
    """Render data stores as Markdown list."""
    if not stores:
        return "- (discovery incomplete)"
    lines = []
    for s in stores[:20]:
        lines.append(f"- **{s.kind}**: `{s.path}` ({s.schema_hint})")
    return "\n".join(lines)


def _render_build_md(build: BuildAndToolingFact) -> str:
    """Render build and tooling as Markdown."""
    lines = []
    lines.append(f"- Package manager: {build.package_manager or 'unknown'}")
    if build.ci_commands:
        lines.append(f"- CI: {', '.join(build.ci_commands[:5])}")
    if build.scripts:
        lines.append(f"- Scripts: {', '.join(build.scripts[:5])}")
    return "\n".join(lines) if lines else "- (discovery incomplete)"


def _render_testing_md(tests: list[TestingFact]) -> str:
    """Render testing surface as Markdown list."""
    if not tests:
        return "- (no test suites discovered)"
    lines = []
    for t in tests[:20]:
        lines.append(f"- **{t.suite}** (`{t.path}`): {t.scope}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Legacy compatibility wrapper
# ---------------------------------------------------------------------------


def repo_map_digest_section_legacy(date: str, repository_type: str) -> str:
    """Legacy wrapper for backward compatibility.

    Creates a minimal StructuralFacts from repository_type string
    and delegates to the new implementation.
    """
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

    return repo_map_digest_section(date, minimal_facts)


def render_repo_map_digest_create_legacy(
    *,
    date: str,
    repo_name: str,
    repository_type: str,
) -> str:
    """Legacy wrapper for backward compatibility.

    Creates a minimal StructuralFacts from repository_type string
    and delegates to the new implementation.
    """
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

    return render_repo_map_digest_create(date=date, repo_name=repo_name, discovery=minimal_facts)
