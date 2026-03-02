from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from governance.domain.strict_exit_evaluator import (
    StrictExitResult,
    evaluate_strict_exit,
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    code: str
    reason: str


def persistence_gate(state: dict[str, Any]) -> GateResult:
    flags = state.get("CommitFlags") if isinstance(state, dict) else None
    if not isinstance(flags, dict):
        return GateResult(ok=False, code="PERSISTENCE_FLAGS_MISSING", reason="commit flags missing")
    if flags.get("PersistenceCommitted") is not True:
        return GateResult(ok=False, code="PERSISTENCE_NOT_COMMITTED", reason="persistence not committed")
    if flags.get("WorkspaceArtifactsCommitted") is not True:
        return GateResult(ok=False, code="ARTIFACTS_NOT_COMMITTED", reason="workspace artifacts not committed")
    return GateResult(ok=True, code="OK", reason="persistence gate satisfied")


def rulebook_gate(*, target_phase: str, loaded_rulebooks: dict[str, Any]) -> GateResult:
    major_token = str(target_phase).split(".", 1)[0].strip()
    try:
        major_phase = int(major_token)
    except ValueError:
        major_phase = 0
    if major_phase < 4:
        return GateResult(ok=True, code="OK", reason="rulebook gate not required")
    if not isinstance(loaded_rulebooks, dict):
        return GateResult(ok=False, code="RULEBOOKS_MISSING", reason="loaded rulebooks missing")
    if loaded_rulebooks.get("anchors_ok") is False:
        return GateResult(ok=False, code="RULEBOOK_ANCHOR_MISSING", reason="rulebook anchors missing")
    if not loaded_rulebooks.get("core") or not loaded_rulebooks.get("profile"):
        return GateResult(ok=False, code="RULEBOOKS_INCOMPLETE", reason="core/profile rulebooks required")
    return GateResult(ok=True, code="OK", reason="rulebook gate satisfied")


def strict_exit_gate(
    *,
    pass_criteria: Sequence[Mapping[str, object]],
    evidence_map: Mapping[str, Mapping[str, object]],
    risk_tier: str = "unknown",
    now_utc: datetime,
    principal_strict: bool,
) -> StrictExitResult:
    """Evaluate the strict-exit gate for a phase transition.

    Delegates to the domain evaluator.  This thin wrapper lives in gate_policy
    so all gate functions share a single import surface for the engine layer.
    """
    return evaluate_strict_exit(
        pass_criteria=pass_criteria,
        evidence_map=evidence_map,
        risk_tier=risk_tier,
        now_utc=now_utc,
        principal_strict=principal_strict,
    )
