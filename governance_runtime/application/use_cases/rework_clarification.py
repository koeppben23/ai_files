"""Deterministic rework clarification classification and state consumption helpers."""

from __future__ import annotations

from typing import Literal, Mapping, MutableMapping

ReworkOutcome = Literal["scope_change", "plan_change", "clarification_only", "insufficient"]

_VAGUE_ONLY_TOKENS: tuple[str, ...] = (
    "passt nicht",
    "so nicht",
    "nochmal",
    "ueberarbeiten",
    "überarbeiten",
    "anders machen",
    "fixen",
)

_SCOPE_TOKENS: tuple[str, ...] = (
    "scope",
    "umfang",
    "anforderung",
    "requirement",
    "ticket",
    "task",
    "auftrag",
    "deliverable",
    "akzeptanz",
    "acceptance",
    "prioritaet",
    "priorität",
    "neue",
    "zusätzlich",
    "zusaetzlich",
)

_PLAN_TOKENS: tuple[str, ...] = (
    "plan",
    "architektur",
    "approach",
    "vorgehen",
    "vorgehensweise",
    "strategie",
    "strategy",
    "sequenz",
    "reihenfolge",
    "struktur",
)

_CLARIFICATION_TOKENS: tuple[str, ...] = (
    "klarstellen",
    "clarify",
    "erklaeren",
    "erklären",
    "begruenden",
    "begründen",
    "praezisieren",
    "präzisieren",
    "formulierung",
    "darstellung",
    "evidence",
)


def classify_rework_clarification(user_text: str, context: Mapping[str, object] | None = None) -> ReworkOutcome:
    """Classify clarification text into deterministic routing outcomes.

    Priority is explicit and stable:
    1) scope_change
    2) plan_change
    3) clarification_only
    4) insufficient
    """

    _ = context
    probe = " ".join(user_text.lower().split())
    if not probe:
        return "insufficient"

    if len(probe) < 12 and any(token == probe for token in _VAGUE_ONLY_TOKENS):
        return "insufficient"

    scope_stable = any(
        phrase in probe
        for phrase in (
            "scope bleibt",
            "task bleibt",
            "auftrag bleibt",
            "umfang bleibt",
            "scope unveraendert",
            "scope unverändert",
        )
    )
    explicit_scope_change = any(
        phrase in probe
        for phrase in (
            "scope aender",
            "scope änder",
            "scope erweit",
            "umfang aender",
            "umfang änder",
            "task aender",
            "task änder",
            "neue anforderung",
            "new requirement",
        )
    )

    scope_hit = any(token in probe for token in _SCOPE_TOKENS)
    if scope_stable and not explicit_scope_change:
        scope_hit = False
    plan_hit = any(token in probe for token in _PLAN_TOKENS)
    clarification_hit = any(token in probe for token in _CLARIFICATION_TOKENS)

    if scope_hit:
        return "scope_change"
    if plan_hit:
        return "plan_change"
    if clarification_hit:
        return "clarification_only"
    return "insufficient"


def derive_next_rail(outcome: ReworkOutcome) -> str | None:
    """Map classification outcome to exactly one next rail or None."""

    if outcome == "scope_change":
        return "/ticket"
    if outcome == "plan_change":
        return "/plan"
    if outcome == "clarification_only":
        return "/continue"
    return None


def is_rework_clarification_active(state: Mapping[str, object]) -> bool:
    """Return True when the state is currently inside rework clarification."""

    phase6_state = str(state.get("phase6_state") or "").strip().lower()
    if phase6_state in ("6.rework", "phase6_changes_requested"):
        return True
    for key in ("active_gate", "ActiveGate", "Gate"):
        value = state.get(key)
        if isinstance(value, str) and value.strip().lower() == "rework clarification gate":
            return True
    return False


def consume_rework_clarification_state(
    state: MutableMapping[str, object],
    *,
    consumed_by: str,
    consumed_at: str = "",
) -> bool:
    """Consume clarification state after a valid /ticket or /plan action.

    Returns True when state was consumed, False when nothing was active.
    """

    if not is_rework_clarification_active(state):
        return False

    if str(state.get("active_gate") or "").strip().lower() == "rework clarification gate":
        state.pop("active_gate", None)

    ngc = str(state.get("next_gate_condition") or "").strip().lower()
    if "clarify requested changes" in ngc or "clarification" in ngc:
        state.pop("next_gate_condition", None)

    state.pop("phase6_state", None)
    state.pop("UserReviewDecision", None)
    state.pop("user_review_decision", None)
    state["rework_clarification_consumed"] = True
    state["rework_clarification_consumed_by"] = consumed_by
    state["rework_clarification_consumed_at"] = str(consumed_at or "set")
    return True
