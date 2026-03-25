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


def _clamp(value: str, *, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _split_compact_items(text: str, *, max_items: int) -> list[str]:
    raw = [part.strip() for part in re.split(r"\n+|;|\d+[.)]\s+", text) if part.strip()]
    if not raw:
        return []
    return [_clamp(item, limit=180) for item in raw[:max_items]]


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
    target_state = str(plan.get("target_state", "") or "").strip()
    risks = str(plan.get("risks", "") or "").strip()
    open_questions = str(plan.get("open_questions", "") or "").strip()

    executive_summary = [
        "Plan objective is captured and ready for decision.",
        "Target state, execution flow, and release gates are documented.",
        "Decision rails are deterministic and fail-closed.",
    ]
    execution_slices = [
        "Execution flow is defined as ordered implementation slices in the technical appendix."
    ]
    risk_items = _split_compact_items(risks, max_items=MAX_RISKS)
    open_items = _split_compact_items(open_questions, max_items=MAX_RISKS)

    if not execution_slices:
        execution_slices = ["Execution slices are documented in the technical appendix."]
    if not risk_items:
        risk_items = ["No explicit risks provided; confirm before approval."]
    if not open_items:
        open_items = ["No open decisions."]

    delta = "Initial plan presentation." if not re_review else "Updated since last review iteration."

    return {
        "title": _clamp(TITLE, limit=80),
        "plan_status_badge": _clamp(PLAN_STATUS_BADGE, limit=60),
        "decision_required": _clamp(DECISION_REQUIRED, limit=180),
        "executive_summary": executive_summary,
        "delta_since_last_review": _clamp(delta, limit=120),
        "scope": _clamp(
            "Scope is defined and traceable in the technical appendix target-state section."
            if target_state
            else "Scope must be confirmed before approval.",
            limit=400,
        ),
        "execution_slices": execution_slices,
        "risks_and_mitigations": risk_items,
        "release_gates": _clamp(
            "Release gates are defined and must remain green before approval."
            if str(plan.get("go_no_go", "") or "").strip()
            else "Release gates must be confirmed before approval.",
            limit=400,
        ),
        "open_decisions": open_items,
        "next_actions": list(NEXT_ACTIONS),
        "language": "en",
    }
