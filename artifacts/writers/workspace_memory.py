from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from governance_runtime.infrastructure.repo_discovery import (
        SemanticFacts,
        ConventionFact,
        PatternFact,
        DefaultFact,
        DeviationFact,
    )


def render_workspace_memory(
    *,
    date: str,
    repo_name: str,
    repo_fingerprint: str,
    semantic: SemanticFacts | None = None,
) -> str:
    """Render workspace-memory.yaml content.
    
    Args:
        date: ISO date string
        repo_name: Repository name
        repo_fingerprint: Repository fingerprint
        semantic: Optional SemanticFacts from discovery
    """
    if semantic is not None:
        return _render_with_semantics(date, repo_name, repo_fingerprint, semantic)
    else:
        return _render_legacy(date, repo_name, repo_fingerprint)


def _render_with_semantics(
    date: str,
    repo_name: str,
    repo_fingerprint: str,
    semantic: SemanticFacts,
) -> str:
    """Render workspace memory with semantic discovery facts."""
    lines = [
        "WorkspaceMemory:",
        '  Version: "2.0"',
        "  Repo:",
        f'    RepoName: "{repo_name}"',
        f'    RepoFingerprint: "{repo_fingerprint}"',
        f'  UpdatedAt: "{date}"',
        "  Provenance:",
        '    Source: "Phase2-Discovery"',
        '    EvidenceMode: "evidence-required"',
        "",
    ]
    
    # Conventions
    lines.append("  Conventions:")
    if semantic.conventions:
        for c in semantic.conventions[:10]:
            lines.append(f'    {c.name}: "{c.description[:80]}"')
    else:
        lines.append("    {}")
    
    lines.append("")
    
    # Patterns
    lines.append("  Patterns:")
    if semantic.patterns:
        for p in semantic.patterns[:10]:
            lines.append(f'    {p.name}: "{p.description[:80]}"')
    else:
        lines.append("    {}")
    
    lines.append("")
    
    # Decisions / Defaults
    lines.append("  Decisions:")
    lines.append("    Defaults:")
    if semantic.defaults:
        for d in semantic.defaults[:10]:
            lines.append(f'      {d.setting}: "{d.value}"')
    else:
        lines.append("      []")
    
    lines.append("")
    
    # Deviations
    lines.append("  Deviations:")
    if semantic.deviations:
        for dev in semantic.deviations[:5]:
            lines.append(f'    - description: "{dev.description[:60]}"')
            lines.append(f'      severity: "{dev.severity}"')
    else:
        lines.append("    []")
    
    lines.append("")
    
    # SSOTs (new section)
    if semantic.ssots:
        lines.append("  SSOTs:")
        for s in semantic.ssots[:10]:
            lines.append(f'    - concern: "{s.concern}"')
            lines.append(f'      path: "{s.path}"')
            lines.append(f'      authority: "{s.authority}"')
        lines.append("")
    
    # Invariants (new section)
    if semantic.invariants:
        lines.append("  Invariants:")
        for i in semantic.invariants[:10]:
            lines.append(f'    - rule: "{i.rule[:80]}"')
            lines.append(f'      category: "{i.category}"')
            if i.enforcement:
                lines.append(f'      enforcement: "{i.enforcement}"')
        lines.append("")
    
    return "\n".join(lines)


def _render_legacy(date: str, repo_name: str, repo_fingerprint: str) -> str:
    """Render workspace memory without semantic facts (legacy)."""
    return "\n".join(
        [
            "WorkspaceMemory:",
            '  Version: "1.0"',
            "  Repo:",
            f'    RepoName: "{repo_name}"',
            f'    RepoFingerprint: "{repo_fingerprint}"',
            f'  UpdatedAt: "{date}"',
            "  Provenance:",
            '    Source: "Phase2+Phase5"',
            '    EvidenceMode: "evidence-required"',
            "  Conventions: {}",
            "  Patterns: {}",
            "  Decisions:",
            "    Defaults: []",
            "  Deviations: []",
            "",
        ]
    )
