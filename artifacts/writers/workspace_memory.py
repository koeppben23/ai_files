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
    
    # Conventions - now with evidence and confidence
    lines.append("  Conventions:")
    if semantic.conventions:
        for c in semantic.conventions[:10]:
            lines.append(f'    {c.name}:')
            lines.append(f'      description: "{c.description[:80]}"')
            lines.append(f'      confidence: "{c.evidence.confidence.value}"')
            lines.append(f'      evidence: "{c.evidence.source}: {c.evidence.reference[:60]}"')
    else:
        lines.append("    {}")
    
    lines.append("")
    
    # Patterns - now with locations and confidence
    lines.append("  Patterns:")
    if semantic.patterns:
        for p in semantic.patterns[:8]:
            lines.append(f'    {p.name}:')
            lines.append(f'      description: "{p.description[:80]}"')
            lines.append(f'      confidence: "{p.evidence.confidence.value}"')
            lines.append(f'      occurrences: {len(p.locations)}')
            if p.locations[:3]:
                for loc in p.locations[:3]:
                    lines.append(f'      - "{loc}"')
    else:
        lines.append("    {}")
    
    lines.append("")
    
    # Decisions / Defaults - now with override info
    lines.append("  Decisions:")
    lines.append("    Defaults:")
    if semantic.defaults:
        for d in semantic.defaults[:10]:
            lines.append(f'      {d.setting}:')
            lines.append(f'        value: "{d.value}"')
            lines.append(f'        confidence: "{d.evidence.confidence.value}"')
            if d.override_path:
                lines.append(f'        override: "{d.override_path}"')
    else:
        lines.append("      []")
    
    lines.append("")
    
    # Deviations - with recommendation
    lines.append("  Deviations:")
    if semantic.deviations:
        for dev in semantic.deviations[:5]:
            lines.append(f'    - description: "{dev.description[:60]}"')
            lines.append(f'      severity: "{dev.severity}"')
            lines.append(f'      expected: "{dev.expected[:50]}"')
            lines.append(f'      observed: "{dev.observed[:50]}"')
            if dev.recommendation:
                lines.append(f'      recommendation: "{dev.recommendation[:60]}"')
    else:
        lines.append("    []")
    
    lines.append("")
    
    # SSOTs - with schema
    if semantic.ssots:
        lines.append("  SSOTs:")
        for s in semantic.ssots[:10]:
            lines.append(f'    - concern: "{s.concern}"')
            lines.append(f'      path: "{s.path}"')
            lines.append(f'      authority: "{s.authority}"')
            lines.append(f'      confidence: "{s.evidence.confidence.value}"')
            if s.schema:
                lines.append(f'      schema: "{s.schema}"')
        lines.append("")
    
    # Invariants - with enforcement details
    if semantic.invariants:
        lines.append("  Invariants:")
        for i in semantic.invariants[:10]:
            lines.append(f'    - rule: "{i.rule[:80]}"')
            lines.append(f'      category: "{i.category}"')
            lines.append(f'      confidence: "{i.evidence.confidence.value}"')
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
