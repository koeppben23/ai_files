"""Effective LLM Policy Compiler.

Parses loaded rulebook and addon content into structured authoring and review
policies. Kernel-owned; produces the effective_llm_policy payload that goes into
LLM context at /implement, Phase 5, and Phase 6.

Architecture:
  LOAD   -> Parse raw markdown content from rulebook files
  RESOLVE -> Apply precedence: global -> master -> profile -> addons
  PROJECT -> Build phase-specific LLM-effective policy blocks
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECTION_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.+)$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
CODE_BLOCK_RE = re.compile(r"```[\w]*\n(.*?)```", re.DOTALL)
BINDING_RE = re.compile(r"\(binding\)", re.IGNORECASE)
MANDATORY_RE = re.compile(r"\(MUST\)|\(MUST\s+WHEN\b", re.IGNORECASE)
SHOULD_RE = re.compile(r"\(SHOULD\)|\(RECOMMENDED\)", re.IGNORECASE)
BINDING_SECTION_RE = re.compile(
    r"^##?\s+(.+?)\s+\((?:binding|must|mandatory)\)",
    re.IGNORECASE,
)
YAML_BLOCK_RE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class RulebookContent:
    """Raw parsed content from a single rulebook source."""

    identifier: str
    source_kind: str
    path: str
    sha256: str
    raw_text: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    binding_items: list[str] = field(default_factory=list)
    must_items: list[str] = field(default_factory=list)
    should_items: list[str] = field(default_factory=list)
    decision_trees: list[str] = field(default_factory=list)
    yaml_blocks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AuthoringPolicy:
    """Compiled authoring policy for /implement."""

    profile_constraints: tuple[str, ...] = ()
    addon_constraints: tuple[str, ...] = ()
    quality_priorities: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    naming_conventions: tuple[str, ...] = ()
    tooling_commands: tuple[str, ...] = ()
    decision_rules: tuple[str, ...] = ()
    governance_addendum: tuple[str, ...] = ()
    profile_anti_patterns: tuple[str, ...] = ()
    definition_of_done: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewPolicy:
    """Compiled review policy for Phase 5 and Phase 6."""

    profile_constraints: tuple[str, ...] = ()
    addon_constraints: tuple[str, ...] = ()
    required_lenses: tuple[dict[str, Any], ...] = ()
    apply_when_relevant_lenses: tuple[dict[str, Any], ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    tier_evidence_minimums: dict[str, list[str]] = field(default_factory=dict)
    decision_rules: tuple[str, ...] = ()
    governance_addendum: tuple[str, ...] = ()


@dataclass(frozen=True)
class EffectiveLLMPolicy:
    """Complete effective LLM policy for a governance run."""

    schema_version: str = "1.0.0"
    compiled_at: str = ""
    source_digest: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    authoring_policy: AuthoringPolicy = field(default_factory=AuthoringPolicy)
    review_policy: ReviewPolicy = field(default_factory=ReviewPolicy)


def parse_rulebook_content(
    identifier: str,
    source_kind: str,
    path: str,
    raw_text: str,
) -> RulebookContent:
    sections: dict[str, list[str]] = {}
    current_section = " preamble"
    current_lines: list[str] = []

    for line in raw_text.splitlines():
        m = SECTION_HEADER_RE.match(line.rstrip())
        if m:
            if current_lines:
                sections[current_section.strip()] = _normalize_lines(current_lines)
                current_lines = []
            current_section = m.group(2).strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_section.strip()] = _normalize_lines(current_lines)

    binding_items = _extract_binding_items(sections)
    must_items = _extract_must_items(sections)
    should_items = _extract_should_items(sections)
    decision_trees = _extract_decision_trees(sections)
    yaml_blocks = _extract_yaml_blocks(sections)

    sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    return RulebookContent(
        identifier=identifier,
        source_kind=source_kind,
        path=path,
        sha256=sha,
        raw_text=raw_text,
        sections=sections,
        binding_items=tuple(binding_items),
        must_items=tuple(must_items),
        should_items=tuple(should_items),
        decision_trees=tuple(decision_trees),
        yaml_blocks=tuple(yaml_blocks),
    )


def _normalize_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.startswith("***"):
            continue
        if stripped.startswith("---"):
            continue
        result.append(stripped)
    return result


def _extract_binding_items(sections: dict[str, list[str]]) -> list[str]:
    items: list[str] = []
    for section_name, lines in sections.items():
        if BINDING_RE.search(section_name):
            for line in lines:
                if line.startswith("- ") or line.startswith("* "):
                    text = line[2:].strip()
                    if text and len(text) > 5:
                        items.append(text)
    return items


def _extract_must_items(sections: dict[str, list[str]]) -> list[str]:
    items: list[str] = []
    for lines in sections.values():
        for line in lines:
            if MANDATORY_RE.search(line):
                text = re.sub(MANDATORY_RE, "", line).strip()
                text = re.sub(r"^[-*]\s*", "", text).strip()
                if text:
                    items.append(text)
    return items


def _extract_should_items(sections: dict[str, list[str]]) -> list[str]:
    items: list[str] = []
    for lines in sections.values():
        for line in lines:
            if SHOULD_RE.search(line):
                text = re.sub(SHOULD_RE, "", line).strip()
                text = re.sub(r"^[-*]\s*", "", text).strip()
                if text:
                    items.append(text)
    return items


def _extract_decision_trees(sections: dict[str, list[str]]) -> list[str]:
    trees: list[str] = []
    for section_name, lines in sections.items():
        if "decision" in section_name.lower() or "tree" in section_name.lower():
            block = "\n".join(lines)
            if len(block) > 20:
                trees.append(block[:500])
    return trees


def _extract_yaml_blocks(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for lines in sections.values():
        block_text = "\n".join(lines)
        for match in YAML_BLOCK_RE.finditer(block_text):
            yaml_text = match.group(1).strip()
            if yaml_text and ":" in yaml_text:
                try:
                    import yaml as _yaml
                    data = _yaml.safe_load(yaml_text)
                    if isinstance(data, dict):
                        blocks.append(data)
                except (ValueError, _yaml.YAMLError):
                    pass
    return blocks


def resolve_authoring_policy(
    core: RulebookContent | None,
    master: RulebookContent | None,
    profile: RulebookContent | None,
    addons: tuple[RulebookContent, ...],
) -> AuthoringPolicy:
    """Build authoring policy with precedence: core -> master -> profile -> addons."""
    global_constraints: list[str] = []
    profile_constraints: list[str] = []
    addon_constraints: list[str] = []
    quality_priorities: list[str] = []
    forbidden_behaviors: list[str] = []
    required_checks: list[str] = []
    naming_conventions: list[str] = []
    tooling_commands: list[str] = []
    decision_rules: list[str] = []
    governance_addendum: list[str] = []
    anti_patterns: list[str] = []
    definition_of_done: list[str] = []

    for rb in [core, master, profile] + list(addons):
        if rb is None:
            continue
        kind = rb.source_kind

        for item in rb.binding_items:
            if kind in ("core", "master"):
                global_constraints.append(item)
            elif kind == "profile":
                profile_constraints.append(item)
            else:
                addon_constraints.append(item)

        for item in rb.must_items:
            if "quality" in item.lower() or "priority" in item.lower():
                quality_priorities.append(item)
            elif "check" in item.lower() or "verification" in item.lower():
                required_checks.append(item)
            elif "forbidden" in item.lower() or "must not" in item.lower():
                forbidden_behaviors.append(item)
            elif "naming" in item.lower() or "convention" in item.lower():
                naming_conventions.append(item)
            elif "tooling" in item.lower() or "command" in item.lower():
                tooling_commands.append(item)
            elif "done" in item.lower() or "complete" in item.lower():
                definition_of_done.append(item)
            elif "anti-pattern" in item.lower():
                anti_patterns.append(item)
            elif kind == "profile":
                profile_constraints.append(item)
            else:
                addon_constraints.append(item)

        for tree in rb.decision_trees:
            decision_rules.append(tree[:300])

    quality_priorities.extend(_infer_quality_priorities(profile))
    governance_addendum.extend(_build_governance_addendum(profile, addons))

    return AuthoringPolicy(
        profile_constraints=tuple(_dedup(profile_constraints)),
        addon_constraints=tuple(_dedup(addon_constraints)),
        quality_priorities=tuple(_dedup(quality_priorities)),
        forbidden_behaviors=tuple(_dedup(forbidden_behaviors)),
        required_checks=tuple(_dedup(required_checks)),
        naming_conventions=tuple(_dedup(naming_conventions)),
        tooling_commands=tuple(_dedup(tooling_commands)),
        decision_rules=tuple(_dedup(decision_rules)),
        governance_addendum=tuple(_dedup(governance_addendum)),
        profile_anti_patterns=tuple(_dedup(anti_patterns)),
        definition_of_done=tuple(_dedup(definition_of_done)),
    )


def resolve_review_policy(
    core: RulebookContent | None,
    master: RulebookContent | None,
    profile: RulebookContent | None,
    addons: tuple[RulebookContent, ...],
) -> ReviewPolicy:
    """Build review policy with precedence: core -> master -> profile -> addons."""
    profile_constraints: list[str] = []
    addon_constraints: list[str] = []
    required_lenses: list[dict[str, Any]] = []
    apply_when_relevant_lenses: list[dict[str, Any]] = []
    forbidden_behaviors: list[str] = []
    required_checks: list[str] = []
    tier_evidence: dict[str, list[str]] = {}
    decision_rules: list[str] = []
    governance_addendum: list[str] = []

    for rb in [core, master, profile] + list(addons):
        if rb is None:
            continue
        kind = rb.source_kind

        for item in rb.binding_items:
            if kind == "profile":
                profile_constraints.append(item)
            elif kind == "addon":
                addon_constraints.append(item)

        for item in rb.must_items:
            if "lens" in item.lower() or "review" in item.lower():
                lens = _parse_lens_item(item)
                if lens:
                    required_lenses.append(lens)
            elif "check" in item.lower() or "verify" in item.lower():
                required_checks.append(item)
            elif "tier" in item.lower() or "evidence" in item.lower():
                _merge_tier_evidence(item, tier_evidence)
            elif kind == "profile":
                profile_constraints.append(item)
            else:
                addon_constraints.append(item)

        for tree in rb.decision_trees:
            decision_rules.append(tree[:300])

    tier_evidence = _resolve_tier_evidence(addons)

    return ReviewPolicy(
        profile_constraints=tuple(_dedup(profile_constraints)),
        addon_constraints=tuple(_dedup(addon_constraints)),
        required_lenses=tuple(_dedup_lenses(required_lenses)),
        apply_when_relevant_lenses=tuple(required_lenses[len(required_lenses) :]),
        forbidden_behaviors=tuple(_dedup(forbidden_behaviors)),
        required_checks=tuple(_dedup(required_checks)),
        tier_evidence_minimums=tier_evidence,
        decision_rules=tuple(_dedup(decision_rules)),
        governance_addendum=tuple(_dedup(governance_addendum)),
    )


def _parse_lens_item(item: str) -> dict[str, Any]:
    text = re.sub(MANDATORY_RE, "", item).strip()
    text = re.sub(r"^[-*]\s*", "", text).strip()
    if len(text) < 5:
        return {}
    return {
        "name": text[:60],
        "focus": text[:120],
        "questions": [],
    }


def _merge_tier_evidence(item: str, tier_evidence: dict[str, list[str]]) -> None:
    text = re.sub(MANDATORY_RE, "", item).strip()
    text = re.sub(r"^[-*]\s*", "", text).strip()
    for tier in ["TIER-LOW", "TIER-MEDIUM", "TIER-HIGH"]:
        if tier in text.upper():
            tier_evidence.setdefault(tier, []).append(text[:200])


def _resolve_tier_evidence(addons: tuple[RulebookContent, ...]) -> dict[str, list[str]]:
    tier_evidence: dict[str, list[str]] = {
        "TIER-LOW": ["build/lint if present", "targeted changed-scope tests"],
        "TIER-MEDIUM": [
            "TIER-LOW evidence",
            "at least one negative-path assertion for changed behavior",
        ],
        "TIER-HIGH": [
            "TIER-MEDIUM evidence",
            "one deterministic resilience/rollback proof",
        ],
    }
    for addon in addons:
        if addon.identifier in ("risk-tiering", "riskTiering"):
            for block in addon.yaml_blocks:
                if isinstance(block, dict):
                    if "TIER-LOW" in str(block):
                        tier_evidence["TIER-LOW"] = [
                            "build/lint if present",
                            "targeted changed-scope tests",
                        ]
                    if "TIER-MEDIUM" in str(block):
                        tier_evidence["TIER-MEDIUM"] = [
                            "TIER-LOW evidence",
                            "negative-path assertion for changed behavior",
                        ]
                    if "TIER-HIGH" in str(block):
                        tier_evidence["TIER-HIGH"] = [
                            "TIER-MEDIUM evidence",
                            "rollback/resilience proof",
                        ]
    return tier_evidence


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedup_lenses(lenses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for lens in lenses:
        key = lens.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(lens)
    return result


def _infer_quality_priorities(profile: RulebookContent | None) -> list[str]:
    if profile is None:
        return []
    priorities: list[str] = []
    for key, lines in profile.sections.items():
        if "quality" in key.lower() or "priority" in key.lower():
            for line in lines:
                if line.startswith("- ") or line.startswith("* "):
                    priorities.append(line[2:].strip())
    return priorities


def _build_governance_addendum(
    profile: RulebookContent | None,
    addons: tuple[RulebookContent, ...],
) -> list[str]:
    addendum: list[str] = []
    if profile:
        intent = profile.sections.get("Intent (binding)", [])
        for line in intent[:2]:
            if len(line) > 10:
                addendum.append(f"Profile intent: {line[:200]}")
    for addon in addons:
        intent = addon.sections.get("Intent (binding)", [])
        for line in intent[:1]:
            if len(line) > 10:
                addendum.append(f"Addon {addon.identifier}: {line[:200]}")
    return addendum


def compute_policy_digest(policy: EffectiveLLMPolicy) -> str:
    """Stable digest for audit and drift detection."""
    payload = json.dumps(
        {
            "authoring": {
                "profile_constraints": list(policy.authoring_policy.profile_constraints),
                "addon_constraints": list(policy.authoring_policy.addon_constraints),
                "required_checks": list(policy.authoring_policy.required_checks),
            },
            "review": {
                "profile_constraints": list(policy.review_policy.profile_constraints),
                "addon_constraints": list(policy.review_policy.addon_constraints),
                "required_checks": list(policy.review_policy.required_checks),
            },
        },
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def to_serializable(policy: EffectiveLLMPolicy) -> dict[str, Any]:
    """Convert to JSON-serializable dict for schema validation and storage."""
    return {
        "schema_version": policy.schema_version,
        "compiled_at": policy.compiled_at,
        "source_digest": policy.source_digest,
        "evidence": policy.evidence,
        "effective_policy": {
            "global_constraints": [],
            "effective_authoring_policy": {
                "profile_constraints": list(policy.authoring_policy.profile_constraints),
                "addon_constraints": list(policy.authoring_policy.addon_constraints),
                "quality_priorities": list(policy.authoring_policy.quality_priorities),
                "forbidden_behaviors": list(policy.authoring_policy.forbidden_behaviors),
                "required_checks": list(policy.authoring_policy.required_checks),
                "naming_conventions": list(policy.authoring_policy.naming_conventions),
                "tooling_commands": list(policy.authoring_policy.tooling_commands),
                "decision_rules": list(policy.authoring_policy.decision_rules),
                "governance_addendum": list(policy.authoring_policy.governance_addendum),
                "profile_anti_patterns": list(policy.authoring_policy.profile_anti_patterns),
                "definition_of_done": list(policy.authoring_policy.definition_of_done),
            },
            "effective_review_policy": {
                "profile_constraints": list(policy.review_policy.profile_constraints),
                "addon_constraints": list(policy.review_policy.addon_constraints),
                "required_lenses": list(policy.review_policy.required_lenses),
                "apply_when_relevant_lenses": list(
                    policy.review_policy.apply_when_relevant_lenses
                ),
                "forbidden_behaviors": list(policy.review_policy.forbidden_behaviors),
                "required_checks": list(policy.review_policy.required_checks),
                "tier_evidence_minimums": policy.review_policy.tier_evidence_minimums,
                "decision_rules": list(policy.review_policy.decision_rules),
                "governance_addendum": list(policy.review_policy.governance_addendum),
            },
        },
    }
