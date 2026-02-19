"""Phase-coupled persistence gate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from governance.application.policies.persistence_policy import (
    ARTIFACT_BUSINESS_RULES,
    ARTIFACT_DECISION_PACK,
    ARTIFACT_REPO_CACHE,
    ARTIFACT_REPO_DIGEST,
    ARTIFACT_WORKSPACE_MEMORY,
    PersistencePolicyInput,
    can_write as can_write_persistence,
)
from governance.application.use_cases.session_state_helpers import session_state_root
from governance.domain.reason_codes import REASON_CODE_NONE

if TYPE_CHECKING:
    from governance.application.ports.gateways import OperatingMode


WORKSPACE_MEMORY_CONFIRMATION = "Persist to workspace memory: YES"


@dataclass(frozen=True)
class PersistencePhaseGateDecision:
    allowed: bool
    reason_code: str
    reason: str


def _phase5_approved(state: Mapping[str, object]) -> bool:
    for key in ("phase5_approved", "Phase5Approved", "phase_5_approved"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _business_rules_executed(state: Mapping[str, object]) -> bool:
    for key in ("business_rules_executed", "BusinessRulesExecuted"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _artifact_kind_from_target_variable(target_variable: str | None) -> str | None:
    if target_variable == "REPO_CACHE_FILE":
        return ARTIFACT_REPO_CACHE
    if target_variable == "REPO_DIGEST_FILE":
        return ARTIFACT_REPO_DIGEST
    if target_variable == "REPO_DECISION_PACK_FILE":
        return ARTIFACT_DECISION_PACK
    if target_variable == "REPO_BUSINESS_RULES_FILE":
        return ARTIFACT_BUSINESS_RULES
    if target_variable == "WORKSPACE_MEMORY_FILE":
        return ARTIFACT_WORKSPACE_MEMORY
    return None


def _confirmation_from_evidence(evidence: Mapping[str, object] | None, *, scope: str, gate: str) -> str:
    if evidence is None:
        return ""
    items = evidence.get("items") if isinstance(evidence, Mapping) else None
    if not isinstance(items, list):
        return ""
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("scope") or "").strip() != scope:
            continue
        if str(item.get("gate") or "").strip() != gate:
            continue
        value = str(item.get("value") or "").strip()
        if value:
            return f"Persist to workspace memory: {value}"
    return ""


def evaluate_phase_coupled_persistence(
    *,
    persistence_write_requested: bool,
    phase: str,
    target_variable: str | None,
    effective_mode: "OperatingMode",
    session_state_document: Mapping[str, object] | None,
    persist_confirmation_evidence: Mapping[str, object] | None,
) -> PersistencePhaseGateDecision:
    if not persistence_write_requested:
        return PersistencePhaseGateDecision(True, REASON_CODE_NONE, "not-applicable")

    artifact_kind = _artifact_kind_from_target_variable(target_variable)
    if artifact_kind is None:
        return PersistencePhaseGateDecision(True, REASON_CODE_NONE, "not-applicable")

    state = session_state_root(session_state_document)
    confirmation = _confirmation_from_evidence(
        persist_confirmation_evidence,
        scope="workspace-memory",
        gate="phase5",
    )
    decision = can_write_persistence(
        PersistencePolicyInput(
            artifact_kind=artifact_kind,
            phase=phase,
            mode=effective_mode,
            gate_approved=_phase5_approved(state),
            business_rules_executed=_business_rules_executed(state),
            explicit_confirmation=confirmation,
        )
    )

    if decision.allowed:
        return PersistencePhaseGateDecision(True, REASON_CODE_NONE, "approved")

    return PersistencePhaseGateDecision(False, decision.reason_code, decision.reason)
