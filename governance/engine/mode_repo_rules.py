"""Mode-aware repo-doc rules and host-permissions orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from typing import Literal, Mapping


RepoDirectiveClass = Literal["constraint", "interactive_directive", "unsafe_directive"]


@dataclass(frozen=True)
class PromptBudget:
    max_total_prompts: int
    max_repo_doc_prompts: int


@dataclass(frozen=True)
class RepoDocEvidence:
    doc_path: str
    doc_hash: str
    classification_summary: dict[str, int]


@dataclass(frozen=True)
class RepoDocClassification:
    directive_class: RepoDirectiveClass
    rule_id: str
    excerpt: str


DEFAULT_PROMPT_BUDGETS: dict[str, PromptBudget] = {
    "user": PromptBudget(max_total_prompts=3, max_repo_doc_prompts=0),
    "pipeline": PromptBudget(max_total_prompts=0, max_repo_doc_prompts=0),
    "agents_strict": PromptBudget(max_total_prompts=10, max_repo_doc_prompts=6),
}


def canonicalize_operating_mode(mode: str) -> str:
    token = str(mode).strip().lower()
    if token in {"user", "pipeline", "agents_strict", "system"}:
        return token
    return "invalid"


def resolve_env_operating_mode(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    token = str(source.get("OPENCODE_OPERATING_MODE", "")).strip()
    if token:
        return canonicalize_operating_mode(token)
    ci = str(source.get("CI", "")).strip().lower()
    if ci and ci not in {"0", "false", "no", "off"}:
        return "pipeline"
    return "user"


UNSAFE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("repo_doc_unsafe_skip_tests", r"\bskip\s+tests?\b"),
    ("repo_doc_unsafe_disable_security", r"\bdisable\s+security\b"),
    ("repo_doc_unsafe_exfiltrate", r"\bexfiltrat(e|ion)\b"),
    ("repo_doc_unsafe_ignore_policy", r"\bignore\s+policy\b"),
    ("repo_doc_unsafe_remote_shell", r"curl\s+[^|]+\|\s*sh"),
)

INTERACTIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("repo_doc_interactive_ask_before_commands", r"ask\s+before\s+running\s+commands?"),
    ("repo_doc_interactive_ask_before_edits", r"ask\s+before\s+modif(y|ying)\s+files?"),
    ("repo_doc_interactive_ask_before_commit", r"ask\s+before\s+committ?(ing)?"),
    ("repo_doc_interactive_ask_before_push", r"ask\s+before\s+push(ing)?"),
)


def compute_repo_doc_hash(text: str) -> str:
    """Return deterministic repo-doc hash."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def classify_repo_doc(text: str) -> list[RepoDocClassification]:
    """Classify repo-doc directives deterministically."""

    lowered = text.lower()
    out: list[RepoDocClassification] = []
    for rule_id, pattern in UNSAFE_PATTERNS:
        match = re.search(pattern, lowered)
        if match is not None:
            excerpt = lowered[max(0, match.start() - 32): min(len(lowered), match.end() + 32)]
            out.append(RepoDocClassification("unsafe_directive", rule_id, excerpt.strip()))
    for rule_id, pattern in INTERACTIVE_PATTERNS:
        match = re.search(pattern, lowered)
        if match is not None:
            excerpt = lowered[max(0, match.start() - 32): min(len(lowered), match.end() + 32)]
            out.append(RepoDocClassification("interactive_directive", rule_id, excerpt.strip()))
    if "mvn test" in lowered or "pytest" in lowered or "npm test" in lowered:
        out.append(RepoDocClassification("constraint", "repo_doc_constraint_toolchain_command", "toolchain command hint"))
    return out


def summarize_classification(items: list[RepoDocClassification]) -> dict[str, int]:
    summary = {"constraint": 0, "interactive_directive": 0, "unsafe_directive": 0}
    for item in items:
        summary[item.directive_class] = summary.get(item.directive_class, 0) + 1
    return summary


def resolve_prompt_budget(mode: str) -> PromptBudget:
    canonical = canonicalize_operating_mode(mode)
    if canonical == "invalid":
        canonical = "pipeline"
    return DEFAULT_PROMPT_BUDGETS.get(canonical, DEFAULT_PROMPT_BUDGETS["user"])
