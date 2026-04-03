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


def _split_list_repr(text: str) -> list[str]:
    compact = text.strip()
    if not compact.startswith("[") or not compact.endswith("]"):
        return []
    inner = compact[1:-1]
    parts = [part.strip().strip("'\"") for part in inner.split(",")]
    return [part for part in parts if part]


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
        return ["Define the concrete implementation steps before approval."]
    slices: list[str] = []
    for idx, part in enumerate(parts[:MAX_EXECUTION_SLICES], 1):
        slices.append(_clamp(f"Step {idx}: {part}", limit=180))
    return slices


def _derive_recommendation(*, objective: str, target_state: str, go_no_go: str) -> tuple[str, list[str]]:
    text = f"{objective} {target_state} {go_no_go}".lower()
    if any(token in text for token in ("reject", "not possible", "cannot proceed", "hard blocker")):
        recommendation = "reject"
    elif any(token in text for token in ("unknown", "unclear", "missing", "tbd", "not defined")):
        recommendation = "changes_requested"
    else:
        recommendation = "approve"
    scope_reason = (
        _clamp(f"Scope is defined as: {target_state}", limit=180)
        if target_state
        else "Scope is not explicit enough yet and should be clarified before approval."
    )
    gate_reason = (
        _clamp(f"Release gate proposal: {go_no_go}", limit=180)
        if go_no_go
        else "Release-gate criteria are not explicit yet and should be confirmed before approval."
    )
    reasons = [
        scope_reason,
        gate_reason,
        "Decision can proceed once the listed scope and gates are accepted.",
    ]
    return recommendation, reasons


def _derive_delivery_scope(*, objective: str, target_flow: str, test_strategy: str) -> list[str]:
    text = f"{objective} {target_flow} {test_strategy}".lower()
    scope: list[str] = []
    for token, label in (
        ("happy", "Happy-path behavior"),
        ("bad", "Bad-path/error behavior"),
        ("corner", "Corner-case handling"),
        ("edge", "Edge-case boundaries"),
        ("performance", "Performance behavior"),
    ):
        if token in text:
            scope.append(label)
    if not scope:
        scope = [
            "Happy-path behavior",
            "Bad-path/error behavior",
            "Edge and corner cases",
        ]
    return [f"[ ] {item}" for item in scope]


def _derive_acceptance_criteria(*, objective: str, test_strategy: str) -> list[str]:
    text = f"{objective} {test_strategy}".lower()
    criteria = [
        "All new and updated tests pass on ubuntu-latest, macos-latest, and windows-latest.",
        "Reason codes are validated against canonical contracts and remain deterministic.",
    ]
    if "pipeline" in text or "binding" in text or "mode" in text:
        criteria.append(
            "No-mixing is proven: direct mode ignores env bindings and pipeline mode fails closed on missing bindings."
        )
    else:
        criteria.append("Plan coverage and targeted checks pass with no critical gaps.")
    return criteria


def _normalize_risks_with_mitigation(risks: str) -> list[str]:
    parsed = _split_list_repr(risks)
    source = parsed if parsed else _split_compact_items(risks, max_items=MAX_RISKS)
    if not source:
        return ["Risk: No explicit risk provided. Mitigation: capture at least one concrete risk before approval."]
    prefix = "Risk: "
    suffix = ". Mitigation: add targeted tests and rollback-safe checks for this risk."
    content_limit = max(3, 180 - len(prefix) - len(suffix))
    normalized: list[str] = []
    for item in source[:MAX_RISKS]:
        cleaned = _clamp(item, limit=content_limit)
        normalized.append(f"{prefix}{cleaned}{suffix}")
    return normalized


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
    test_strategy = str(plan.get("test_strategy", "") or "").strip()
    risks = str(plan.get("risks", "") or "").strip()
    open_questions = str(plan.get("open_questions", "") or "").strip()
    recommendation, recommendation_reasons = _derive_recommendation(
        objective=objective,
        target_state=target_state,
        go_no_go=go_no_go,
    )
    delivery_scope = _derive_delivery_scope(
        objective=objective,
        target_flow=target_flow,
        test_strategy=test_strategy,
    )
    acceptance_criteria = _derive_acceptance_criteria(
        objective=objective,
        test_strategy=test_strategy,
    )

    executive_summary = [
        _clamp(objective or "Define a concrete objective before approval.", limit=180),
        _clamp(target_state or "Define an explicit target state before approval.", limit=180),
        _clamp(go_no_go or "Define explicit go/no-go criteria before approval.", limit=180),
    ]
    execution_slices = _execution_slice_signals(target_flow)
    risk_items = _normalize_risks_with_mitigation(risks)
    open_items = _split_compact_items(open_questions, max_items=MAX_RISKS)

    if not execution_slices:
        execution_slices = ["Define concrete execution slices before approval."]
    if not risk_items:
        risk_items = ["No explicit risks provided; confirm before approval."]
    if not open_items:
        open_items = [
            "Confirm final scope boundaries for this approval.",
            "Confirm release-gate pass criteria before rollout.",
        ]

    delta = "Initial plan presentation." if not re_review else "Updated since last review iteration."

    return {
        "title": _clamp(TITLE, limit=80),
        "plan_status_badge": _clamp(PLAN_STATUS_BADGE, limit=60),
        "decision_required": _clamp(DECISION_REQUIRED, limit=180),
        "recommendation": recommendation,
        "recommendation_reasons": recommendation_reasons,
        "delivery_scope": delivery_scope,
        "acceptance_criteria": acceptance_criteria,
        "executive_summary": executive_summary,
        "delta_since_last_review": _clamp(delta, limit=120),
        "scope": _clamp(
            f"Deliver the defined target state: {target_state}"
            if target_state
            else "The implementation scope is not explicit enough for approval.",
            limit=400,
        ),
        "execution_slices": execution_slices,
        "risks_and_mitigations": risk_items,
        "release_gates": _clamp(
            f"Approval gate: {go_no_go}"
            if go_no_go
            else "Approval requires explicit release-gate criteria.",
            limit=400,
        ),
        "open_decisions": open_items,
        "changes_requested_actions": [
            "Specify exactly which missing scenarios or constraints must be added.",
            "Attach one concrete acceptance criterion that can be verified in CI.",
        ],
        "next_actions": list(NEXT_ACTIONS),
        "language": "en",
    }


def build_machine_requirements(plan: Mapping[str, object]) -> list[dict[str, object]]:
    """Build strictly compilable machine requirements from structured plan fields.

    This function is the only authoritative source for compiled requirement
    contracts in Phase 5. It intentionally excludes presentation-only text.
    """
    objective = str(plan.get("objective", "") or "").strip()
    target_flow = str(plan.get("target_flow", "") or "").strip()
    go_no_go = str(plan.get("go_no_go", "") or "").strip()
    test_strategy = str(plan.get("test_strategy", "") or "").strip()

    def _norm_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    presentation = plan.get("presentation_contract")
    if isinstance(presentation, Mapping):
        scope_source = presentation.get("delivery_scope")
    else:
        scope_source = plan.get("delivery_scope")

    hotspots = [
        "governance_runtime/entrypoints/session_reader.py",
        "governance_runtime/entrypoints/implement_start.py",
        "governance_runtime/entrypoints/review_decision_persist.py",
    ]

    requirements: list[dict[str, object]] = []

    if objective:
        requirements.append(
            {
                "title": objective,
                "kind": "required_behavior",
                "required_behavior": f"Implement: {objective}",
                "forbidden_behavior": f"forbid state: {objective} not satisfied",
                "code_hotspots": hotspots,
                "verification_methods": [
                    "behavioral_verification",
                    "live_flow_verification",
                    "static_verification",
                ],
            }
        )

    flow_items = _split_compact_items(target_flow, max_items=MAX_EXECUTION_SLICES)
    for idx, item in enumerate(flow_items, 1):
        requirements.append(
            {
                "title": f"Execution step {idx}: {item}",
                "kind": "required_behavior",
                "required_behavior": f"Implement execution step {idx}: {item}",
                "forbidden_behavior": f"forbid state: execution step {idx} missing ({item})",
                "code_hotspots": hotspots,
                "verification_methods": [
                    "behavioral_verification",
                    "live_flow_verification",
                    "static_verification",
                ],
            }
        )

    if go_no_go:
        requirements.append(
            {
                "title": f"Release gate: {go_no_go}",
                "kind": "state_expectation",
                "required_behavior": f"Satisfy release gate: {go_no_go}",
                "forbidden_behavior": f"forbid state: release gate unmet ({go_no_go})",
                "code_hotspots": hotspots,
                "verification_methods": [
                    "behavioral_verification",
                    "receipts_verification",
                    "static_verification",
                ],
            }
        )

    for item in _norm_list(scope_source):
        normalized = item.replace("[ ]", "").strip()
        if not normalized:
            continue
        requirements.append(
            {
                "title": normalized,
                "kind": "required_behavior",
                "required_behavior": f"Implement scope item: {normalized}",
                "forbidden_behavior": f"forbid state: scope item missing ({normalized})",
                "code_hotspots": hotspots,
                "verification_methods": [
                    "behavioral_verification",
                    "live_flow_verification",
                    "static_verification",
                ],
            }
        )

    if test_strategy:
        requirements.append(
            {
                "title": f"Test strategy: {test_strategy}",
                "kind": "state_expectation",
                "required_behavior": f"Apply test strategy: {test_strategy}",
                "forbidden_behavior": f"forbid state: test strategy not applied ({test_strategy})",
                "code_hotspots": hotspots,
                "verification_methods": [
                    "behavioral_verification",
                    "live_flow_verification",
                    "static_verification",
                ],
            }
        )

    deduped: list[dict[str, object]] = []
    seen_titles: set[str] = set()
    for req in requirements:
        title = str(req.get("title") or "").strip().lower()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        deduped.append(req)

    return deduped
