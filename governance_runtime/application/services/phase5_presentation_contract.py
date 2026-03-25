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
_STOPWORDS = {
    "with",
    "that",
    "this",
    "from",
    "into",
    "will",
    "must",
    "have",
    "been",
    "were",
    "when",
    "where",
    "then",
    "than",
    "only",
    "plan",
    "state",
    "flow",
}


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


def _keyword_signal(text: str, *, max_terms: int = 6) -> str:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
    terms: list[str] = []
    for token in tokens:
        if token in _STOPWORDS:
            continue
        if token in terms:
            continue
        terms.append(token)
        if len(terms) >= max_terms:
            break
    if not terms:
        return "no clear signal captured"
    return ", ".join(terms)


def _execution_slice_signals(target_flow: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n+|\d+[.)]\s+", target_flow) if part.strip()]
    if not parts:
        return ["Execution flow is present; key slice signals are unavailable."]
    slices: list[str] = []
    for idx, part in enumerate(parts[:MAX_EXECUTION_SLICES], 1):
        slices.append(_clamp(f"Slice {idx} signal: {_keyword_signal(part)}.", limit=180))
    return slices


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
    go_no_go = str(plan.get("go_no_go", "") or "").strip()
    risks = str(plan.get("risks", "") or "").strip()
    open_questions = str(plan.get("open_questions", "") or "").strip()

    executive_summary = [
        _clamp(f"Objective signal: {_keyword_signal(objective)}.", limit=180),
        _clamp(f"Target-state signal: {_keyword_signal(target_state)}.", limit=180),
        _clamp(f"Go/No-Go signal: {_keyword_signal(go_no_go)}.", limit=180),
    ]
    execution_slices = _execution_slice_signals(target_flow)
    risk_items = _split_compact_items(risks, max_items=MAX_RISKS)
    open_items = _split_compact_items(open_questions, max_items=MAX_RISKS)

    if not execution_slices:
        execution_slices = ["Execution flow is present; key slice signals are unavailable."]
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
            f"Scope signal: {_keyword_signal(target_state)}."
            if target_state
            else "Scope must be confirmed before approval.",
            limit=400,
        ),
        "execution_slices": execution_slices,
        "risks_and_mitigations": risk_items,
        "release_gates": _clamp(
            f"Release-gate signal: {_keyword_signal(go_no_go)}."
            if go_no_go
            else "Release gates must be confirmed before approval.",
            limit=400,
        ),
        "open_decisions": open_items,
        "next_actions": list(NEXT_ACTIONS),
        "language": "en",
    }
