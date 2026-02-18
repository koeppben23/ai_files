from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PrecedenceDecision:
    decision: Literal["allow", "deny"]
    reason_code: str
    winner_layer: str
    loser_layer: str


def resolve_widening_precedence(
    *,
    mode: str,
    widening_approved: bool,
    reason_code: str,
    applied_reason_code: str,
) -> PrecedenceDecision:
    if mode == "pipeline":
        return PrecedenceDecision(
            decision="deny",
            reason_code=reason_code,
            winner_layer="mode_policy",
            loser_layer="repo_doc_constraints",
        )
    if widening_approved:
        return PrecedenceDecision(
            decision="allow",
            reason_code=applied_reason_code,
            winner_layer="mode_policy",
            loser_layer="repo_doc_constraints",
        )
    return PrecedenceDecision(
        decision="deny",
        reason_code=reason_code,
        winner_layer="mode_policy",
        loser_layer="repo_doc_constraints",
    )
