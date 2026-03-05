"""Target path parsing and output request helpers."""

from __future__ import annotations

import re
from typing import Literal


VARIABLE_CAPTURE = re.compile(r"^\$\{([A-Z0-9_]+)\}")

# Semantic output class type matching phase_api.yaml output_policy classes
OutputClass = Literal[
    "plan",
    "review",
    "risk_analysis",
    "test_strategy",
    "gate_check",
    "rollback_plan",
    "review_questions",
    "consolidated_review_plan",
    "implementation",
    "patch",
    "diff",
    "code_delivery",
    "unknown",
]

# Structural classification: map action keywords to semantic output classes.
# This is NOT phrase-matching or NLP — it classifies the *category* of output
# the requested action would produce.
_IMPLEMENTATION_SIGNALS: tuple[str, ...] = (
    "implement", "code", "write code", "generate code", "deliver",
    "build", "create file", "scaffold", "produce", "start coding",
    "begin implementation", "write the",
)

_PATCH_SIGNALS: tuple[str, ...] = (
    "patch", "apply patch", "hot-fix", "hotfix",
)

_DIFF_SIGNALS: tuple[str, ...] = (
    "diff", "show diff", "generate diff", "unified diff",
)

_CODE_DELIVERY_SIGNALS: tuple[str, ...] = (
    "deliver code", "ship", "deploy artifact", "release code",
    "hand off code", "provide code", "output code",
)

_PLAN_SIGNALS: tuple[str, ...] = (
    "plan", "outline", "design", "architect", "propose",
    "draft", "strategy", "approach",
)

_REVIEW_SIGNALS: tuple[str, ...] = (
    "review", "evaluate", "assess", "audit", "inspect",
    "examine", "check", "verify", "validate",
)

_RISK_SIGNALS: tuple[str, ...] = (
    "risk", "risk analysis", "risk assessment", "threat",
)

_TEST_STRATEGY_SIGNALS: tuple[str, ...] = (
    "test strategy", "test plan", "test approach", "testing",
)

_GATE_CHECK_SIGNALS: tuple[str, ...] = (
    "gate check", "gate", "readiness", "gate evaluation",
)

_ROLLBACK_SIGNALS: tuple[str, ...] = (
    "rollback", "rollback plan", "revert plan", "undo plan",
)


def extract_target_variable(target_path: str) -> str | None:
    """Extract canonical variable token from target path string."""

    match = VARIABLE_CAPTURE.match(target_path.strip())
    if match is None:
        return None
    return match.group(1)


def classify_output_class(requested_action: str | None) -> OutputClass:
    """Classify a requested action into a semantic output class.

    Uses structural keyword matching against output class categories defined
    in phase_api.yaml.  Fail-closed: unrecognized actions default to
    'implementation' (the most restrictive classification) to prevent bypass.
    """
    action = (requested_action or "").strip().lower()
    if not action:
        return "unknown"

    # Check forbidden classes first (implementation-adjacent) — order matters
    # for fail-closed behavior
    if any(sig in action for sig in _CODE_DELIVERY_SIGNALS):
        return "code_delivery"
    if any(sig in action for sig in _PATCH_SIGNALS):
        return "patch"
    if any(sig in action for sig in _DIFF_SIGNALS):
        return "diff"

    # Check allowed review-phase classes
    if any(sig in action for sig in _RISK_SIGNALS):
        return "risk_analysis"
    if any(sig in action for sig in _TEST_STRATEGY_SIGNALS):
        return "test_strategy"
    if any(sig in action for sig in _GATE_CHECK_SIGNALS):
        return "gate_check"
    if any(sig in action for sig in _ROLLBACK_SIGNALS):
        return "rollback_plan"
    if any(sig in action for sig in _REVIEW_SIGNALS):
        return "review"
    if any(sig in action for sig in _PLAN_SIGNALS):
        return "plan"

    # Implementation signals checked after allowed classes
    if any(sig in action for sig in _IMPLEMENTATION_SIGNALS):
        return "implementation"

    # Fail-closed: unrecognized actions are classified as implementation
    # to prevent bypass via novel synonyms
    return "implementation"


def is_code_output_request(requested_action: str | None) -> bool:
    """Fail-closed: any non-empty action in phase 4 is treated as a code-output
    request unless it matches a known read-only / observation-only allowlist.
    This prevents denylist bypass via synonym substitution (A8-F01)."""
    action = (requested_action or "").strip().lower()
    if not action:
        return False
    safe_patterns = (
        "review", "explain", "summarize", "describe", "list",
        "check", "verify", "inspect", "read", "show", "status",
        "plan", "outline", "analyse", "analyze", "compare",
    )
    return not any(token in action for token in safe_patterns)
