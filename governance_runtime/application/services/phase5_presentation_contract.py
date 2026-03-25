"""Phase-5 presentation contract (English-only, deterministic)."""

from __future__ import annotations

import re
from typing import Mapping

TITLE = "PHASE 5 · PLAN FOR APPROVAL"
PLAN_STATUS_BADGE = "PLAN (not implemented)"
DECISION_REQUIRED = "Decision required: choose approve, changes_requested, or reject."

NEXT_ACTIONS = (
    "/review-decision approve",
    "/review-decision changes_requested",
    "/review-decision reject",
)

MAX_EXECUTIVE_SUMMARY_ITEMS = 5
MAX_EXECUTION_SLICES = 7
MAX_RISKS = 5


def _split_compact_items(text: str, *, max_items: int) -> list[str]:
    raw = [part.strip() for part in re.split(r"\n+|;|\d+[.)]\s+", text) if part.strip()]
    if not raw:
        return []
    return raw[:max_items]


def _obvious_non_english_score(text: str) -> int:
    normalized = f" {text.lower()} "
    marker_groups = (
        (" und ", " nicht ", " der ", " die ", " das ", " fuer ", " für "),
        (" et ", " est ", " des ", " les ", " une ", " avec "),
        (" que ", " para ", " con ", " los ", " las ", " una "),
    )
    score = 0
    for markers in marker_groups:
        hits = sum(1 for marker in markers if marker in normalized)
        if hits >= 2:
            score += hits
    return score


def english_violations(plan: Mapping[str, object]) -> list[str]:
    """Return deterministic language violations for required plan fields."""
    fields = (
        "objective",
        "target_state",
        "target_flow",
        "state_machine",
        "blocker_taxonomy",
        "audit",
        "go_no_go",
        "test_strategy",
    )
    violations: list[str] = []
    for name in fields:
        value = str(plan.get(name, "") or "").strip()
        if not value:
            continue
        if _obvious_non_english_score(value) > 0:
            violations.append(f"non-english-content:{name}")
    return violations


def build_presentation_contract(plan: Mapping[str, object], *, re_review: bool = False) -> dict[str, object]:
    """Build deterministic Phase-5 presentation contract payload."""
    objective = str(plan.get("objective", "") or "").strip()
    target_state = str(plan.get("target_state", "") or "").strip()
    target_flow = str(plan.get("target_flow", "") or "").strip()
    risks = str(plan.get("risks", "") or "").strip()
    open_questions = str(plan.get("open_questions", "") or "").strip()
    go_no_go = str(plan.get("go_no_go", "") or "").strip()

    executive_summary = _split_compact_items(
        f"{objective}; {target_state}; {go_no_go}",
        max_items=MAX_EXECUTIVE_SUMMARY_ITEMS,
    )
    execution_slices = _split_compact_items(target_flow, max_items=MAX_EXECUTION_SLICES)
    risk_items = _split_compact_items(risks, max_items=MAX_RISKS)
    open_items = _split_compact_items(open_questions, max_items=MAX_RISKS)

    if not executive_summary:
        executive_summary = ["Plan objective captured and ready for decision."]
    if not execution_slices:
        execution_slices = ["Execution slices not explicitly provided."]
    if not risk_items:
        risk_items = ["No explicit risks provided."]
    if not open_items:
        open_items = ["No open decisions."]

    delta = "Initial plan presentation." if not re_review else "Updated since last review iteration."

    return {
        "title": TITLE,
        "plan_status_badge": PLAN_STATUS_BADGE,
        "decision_required": DECISION_REQUIRED,
        "executive_summary": executive_summary,
        "delta_since_last_review": delta,
        "scope": target_state or "Scope must be confirmed before approval.",
        "execution_slices": execution_slices,
        "risks_and_mitigations": risk_items,
        "release_gates": go_no_go or "Release gates must be confirmed before approval.",
        "open_decisions": open_items,
        "next_actions": list(NEXT_ACTIONS),
        "language": "en",
    }
