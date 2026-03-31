from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from governance_runtime.infrastructure.repo_discovery import SemanticFacts


def decision_pack_section(
    date: str,
    date_compact: str,
    semantic: SemanticFacts | None = None,
) -> str:
    """Render decision pack section.
    
    With semantic facts, generates curated decisions based on discovered
    SSOTs, invariants, and critical paths.
    """
    lines = [
        f"## Decision Pack -- {date}",
        "",
    ]
    
    if semantic is not None and (semantic.ssots or semantic.invariants):
        lines.extend(_render_semantic_decisions(date_compact, semantic))
    else:
        lines.extend(_render_legacy_decisions(date_compact))
    
    return "\n".join(lines)


def _render_legacy_decisions(date_compact: str) -> list[str]:
    """Render fallback decisions when no semantic facts available."""
    return [
        "D-001: Record Business Rules bootstrap outcome",
        f"ID: DP-{date_compact}-001",
        "Status: automatic",
        "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
        "Policy: business-rules-status.md is always written; business-rules.md is written only when outcome=extracted with extractor evidence.",
        "What would change it: scope evidence or Phase 1.5 extraction state.",
        "",
    ]


def _render_semantic_decisions(date_compact: str, semantic: SemanticFacts) -> list[str]:
    """Render decisions derived from semantic discovery.
    
    Only high-quality curated decisions - not every fact is a decision.
    """
    lines: list[str] = []
    decision_num = 1
    
    # SSOT decisions - where is truth for critical concerns
    ssots_by_authority: dict[str, list] = {}
    for s in semantic.ssots:
        ssots_by_authority.setdefault(s.authority, []).append(s)
    
    if ssots_by_authority.get("spec-ssot"):
        spec = ssots_by_authority["spec-ssot"][0]
        lines.extend([
            f"D-{decision_num:03d}: Phase routing truth is in spec",
            f"ID: DP-{date_compact}-{decision_num:03d}",
            "Status: authoritative",
            f"Action: Always consult {spec.path} for phase ordering and transitions.",
            "Policy: phase_api.yaml is the only truth for routing - never override with heuristics.",
            "What would change it: spec schema change or new phase added.",
            "",
        ])
        decision_num += 1
    
    # Invariant decisions - what must not break
    high_confidence_invariants = [i for i in semantic.invariants if i.evidence.confidence.value == "high"]
    if high_confidence_invariants:
        invariant_list = "; ".join([i.category for i in high_confidence_invariants[:3]])
        lines.extend([
            f"D-{decision_num:03d}: Enforce invariants before any structural change",
            f"ID: DP-{date_compact}-{decision_num:03d}",
            "Status: mandatory",
            f"Action: Verify these invariant categories remain intact: {invariant_list}.",
            "Policy: Any change that violates a high-confidence invariant requires explicit review.",
            "What would change it: invariant evidence invalidated or category refactored.",
            "",
        ])
        decision_num += 1
    
    # Convention decision - established patterns
    high_conventions = [c for c in semantic.conventions if c.evidence.confidence.value == "high"]
    if len(high_conventions) >= 2:
        convention_names = ", ".join([c.name for c in high_conventions[:3]])
        lines.extend([
            f"D-{decision_num:03d}: Follow established conventions for new code",
            f"ID: DP-{date_compact}-{decision_num:03d}",
            "Status: recommended",
            f"Action: New code should follow: {convention_names}.",
            "Policy: Deviations from established conventions should be documented in decision-pack.",
            "What would change it: convention evidence invalidated by majority deviation.",
            "",
        ])
        decision_num += 1
    
    # Always include business rules decision
    lines.extend([
        f"D-{decision_num:03d}: Record Business Rules bootstrap outcome",
        f"ID: DP-{date_compact}-{decision_num:03d}",
        "Status: automatic",
        "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
        "Policy: business-rules-status.md is always written; business-rules.md is written only when outcome=extracted with extractor evidence.",
        "What would change it: scope evidence or Phase 1.5 extraction state.",
        "",
    ])
    
    return lines


def render_decision_pack_create(
    *,
    date: str,
    date_compact: str,
    repo_name: str,
    semantic: SemanticFacts | None = None,
) -> str:
    section = decision_pack_section(date, date_compact, semantic)
    return "# Decision Pack\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"
