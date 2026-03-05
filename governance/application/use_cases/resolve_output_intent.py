"""Response Intent Resolver — structural context-based output intent resolution.

This module implements the **primary** output-class determination layer.
It resolves the expected output intent from structured phase/gate context
*before* text generation, replacing reactive keyword-matching as the
canonical source of output-class decisions.

Three-tier validation hierarchy:
    1. **Primary:** This resolver — structural context-based, pre-generation
    2. **Secondary:** ``classify_output_class()`` keyword matcher — fallback + drift detection
    3. **Tertiary:** ``response_formatter.py`` re-check — defense-in-depth on final payload

Design invariants:
    - ``phase_api.yaml`` is the sole SSOT for output policy
    - Policy inheritance: ``5.*`` tokens inherit from token ``"5"`` unless overridden
    - Fail-closed: unknown context → restrictive fallback, NOT permissive pass-through
    - ``policy_resolution_status`` contract rules:
        * ``"resolved"``   → Policy is authoritative; keyword matcher is drift-detection only
        * ``"unbounded"``  → Phase deliberately has no output-class restrictions; keyword matcher logs but does NOT block
        * ``"unresolved"`` → Could not determine policy; restrictive fallback active; keyword matcher MAY block risky classes

Placement: Application layer (not kernel, not engine).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from governance.domain.phase_state_machine import (
    PhaseOutputPolicy,
    PlanDiscipline,
    resolve_phase_output_policy,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

PrimaryIntent = Literal[
    "system_bootstrap",       # Phase 0, 1.x
    "repo_discovery",         # Phase 2
    "api_inventory",          # Phase 3A
    "collect_input",          # Phase 4 (self-loop)
    "review_architecture",    # Phase 5 (stay)
    "gate_evaluation",        # Phase 5.x (sub-graph transitions)
    "terminal_summary",       # Phase 6 (stay)
    "unknown",                # Fail-closed
]

IntentResolutionSource = Literal[
    "phase_api_policy",       # Explicit output_policy from phase_api.yaml
    "structural_inference",   # Derived from route_strategy + phase_token
    "fail_closed_fallback",   # Unknown context, restrictive defaults
]


# ---------------------------------------------------------------------------
# Restrictive fallback policy (fail-closed, NOT fail-open)
# ---------------------------------------------------------------------------

_RESTRICTIVE_FALLBACK_POLICY = PhaseOutputPolicy(
    allowed_output_classes=("plan", "review", "gate_check"),
    forbidden_output_classes=("implementation", "patch", "diff", "code_delivery"),
    plan_discipline=PlanDiscipline(),
)


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedOutputIntent:
    """Immutable resolved output intent for one orchestration cycle.

    Contract rules for ``policy_resolution_status``:

    +--------------+-------------------------------------------------------+
    | Status       | Behavior                                              |
    +--------------+-------------------------------------------------------+
    | ``resolved`` | Policy is authoritative.  Keyword matcher runs for    |
    |              | drift-detection only.  If keyword disagrees → log     |
    |              | warning, do NOT block.                                |
    +--------------+-------------------------------------------------------+
    | ``unbounded``| Phase deliberately has no output-class restrictions.   |
    |              | Keyword matcher logs but does NOT block.               |
    +--------------+-------------------------------------------------------+
    | ``unresolved``| Could not determine policy.  Restrictive fallback     |
    |              | active.  Keyword matcher MAY block risky classes.      |
    +--------------+-------------------------------------------------------+
    """

    effective_output_policy: PhaseOutputPolicy | None
    primary_intent: PrimaryIntent
    source: IntentResolutionSource
    policy_resolution_status: Literal["resolved", "unbounded", "unresolved"]
    fallback_classification_used: bool = False


# ---------------------------------------------------------------------------
# Intent inference from phase token
# ---------------------------------------------------------------------------

# Token prefix → PrimaryIntent mapping.
# 5.x tokens (5.3, 5.4, 5.5, 5.6) are always gate_evaluation (token-based rule).
_TOKEN_INTENT_MAP: dict[str, PrimaryIntent] = {
    "0": "system_bootstrap",
    "1": "system_bootstrap",
    "1.1": "system_bootstrap",
    "1.2": "system_bootstrap",
    "1.5": "system_bootstrap",
    "2": "repo_discovery",
    "2.1": "repo_discovery",
    "3A": "api_inventory",
    "4": "collect_input",
    "5": "review_architecture",
    "5.3": "gate_evaluation",
    "5.4": "gate_evaluation",
    "5.5": "gate_evaluation",
    "5.6": "gate_evaluation",
    "6": "terminal_summary",
}


def _infer_primary_intent(phase_token: str) -> PrimaryIntent:
    """Infer primary intent from phase token.

    Token-based rule: 5.x sub-graph tokens → gate_evaluation,
    regardless of route_strategy.  This is the driftfree variant.
    """
    normalized = phase_token.strip().upper()
    if normalized in _TOKEN_INTENT_MAP:
        return _TOKEN_INTENT_MAP[normalized]

    # Fallback: recognize X.Y patterns for major phases
    match = re.match(r"^(\d+)", normalized)
    if match:
        major = match.group(1)
        if major in _TOKEN_INTENT_MAP:
            # Sub-tokens of a known major phase inherit their parent's intent
            # EXCEPT 5.x which is explicitly mapped above
            return _TOKEN_INTENT_MAP[major]

    return "unknown"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def resolve_output_intent(
    *,
    phase_token: str,
    route_strategy: str,
    active_gate: str = "",
) -> ResolvedOutputIntent:
    """Resolve output intent from structured phase/gate context.

    Resolution hierarchy:
        1. Explicit ``output_policy`` in phase_api.yaml
           → ``source="phase_api_policy"``, ``status="resolved"``
        2. Known token, no policy
           → ``source="structural_inference"``, ``status="unbounded"``,
           ``effective_output_policy=None``
        3. Unknown token / broken context
           → ``source="fail_closed_fallback"``, ``status="unresolved"``,
           ``effective_output_policy=_RESTRICTIVE_FALLBACK_POLICY``

    Parameters
    ----------
    phase_token:
        Current phase token (e.g., ``"5"``, ``"5.3"``, ``"4"``).
    route_strategy:
        Routing strategy from kernel (``"stay"`` or ``"next"``).
        NOT used for PrimaryIntent determination within 5.x sub-graph.
    active_gate:
        Supplementary gate context.  NOT a policy source.
    """
    token = (phase_token or "").strip()
    strategy = (route_strategy or "").strip().lower()

    # Infer primary intent (token-based, driftfree)
    primary_intent = _infer_primary_intent(token)

    # Tier 1: Try explicit output_policy from phase_api.yaml
    if token:
        policy = resolve_phase_output_policy(token)
        if policy is not None:
            logger.debug(
                "resolve_output_intent: phase_token=%s → resolved (phase_api_policy)",
                token,
            )
            return ResolvedOutputIntent(
                effective_output_policy=policy,
                primary_intent=primary_intent,
                source="phase_api_policy",
                policy_resolution_status="resolved",
                fallback_classification_used=False,
            )

    # Tier 2: Known token, no policy → unbounded
    if token and primary_intent != "unknown":
        logger.debug(
            "resolve_output_intent: phase_token=%s → unbounded (structural_inference)",
            token,
        )
        return ResolvedOutputIntent(
            effective_output_policy=None,
            primary_intent=primary_intent,
            source="structural_inference",
            policy_resolution_status="unbounded",
            fallback_classification_used=False,
        )

    # Tier 3: Unknown token / broken context → fail-closed
    logger.warning(
        "resolve_output_intent: phase_token=%r → unresolved (fail_closed_fallback)",
        token,
    )
    return ResolvedOutputIntent(
        effective_output_policy=_RESTRICTIVE_FALLBACK_POLICY,
        primary_intent="unknown",
        source="fail_closed_fallback",
        policy_resolution_status="unresolved",
        fallback_classification_used=False,
    )


__all__ = [
    "IntentResolutionSource",
    "PrimaryIntent",
    "ResolvedOutputIntent",
    "resolve_output_intent",
]
