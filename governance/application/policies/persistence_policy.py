from __future__ import annotations

from dataclasses import dataclass

from governance.domain.phase_state_machine import normalize_phase_token
from governance.domain.reason_codes import (
    PERSIST_CONFIRMATION_INVALID,
    PERSIST_CONFIRMATION_REQUIRED,
    PERSIST_DISALLOWED_IN_PIPELINE,
    PERSIST_GATE_NOT_APPROVED,
    PERSIST_PHASE_MISMATCH,
    REASON_CODE_NONE,
)


ARTIFACT_REPO_CACHE = "REPO_CACHE_FILE"
ARTIFACT_REPO_DIGEST = "REPO_DIGEST_FILE"
ARTIFACT_DECISION_PACK = "REPO_DECISION_PACK_FILE"
ARTIFACT_BUSINESS_RULES = "REPO_BUSINESS_RULES_FILE"
ARTIFACT_WORKSPACE_MEMORY = "WORKSPACE_MEMORY_FILE"


@dataclass(frozen=True)
class PersistencePolicyInput:
    artifact_kind: str
    phase: str
    mode: str
    gate_approved: bool
    business_rules_executed: bool
    explicit_confirmation: str


@dataclass(frozen=True)
class PersistencePolicyDecision:
    allowed: bool
    reason_code: str
    reason: str


_PHASE_RANK: dict[str, int] = {
    "1": 10,
    "1.1": 11,
    "1.2": 12,
    "1.3": 13,
    "1.5": 15,
    "2": 20,
    "2.1": 21,
    "3A": 30,
    "3B-1": 31,
    "3B-2": 32,
    "4": 40,
    "5": 50,
    "5.3": 53,
    "5.4": 54,
    "5.5": 55,
    "5.6": 56,
    "6": 60,
}


def _rank(phase: str) -> int:
    token = normalize_phase_token(phase)
    return _PHASE_RANK.get(token, -1)


def can_write(inputs: PersistencePolicyInput) -> PersistencePolicyDecision:
    artifact = inputs.artifact_kind.strip()
    phase_rank = _rank(inputs.phase)
    mode = inputs.mode.strip().lower()

    if artifact in {ARTIFACT_REPO_CACHE, ARTIFACT_REPO_DIGEST, ARTIFACT_DECISION_PACK}:
        if phase_rank < _PHASE_RANK["2"]:
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "artifact-requires-phase-2-or-later")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_BUSINESS_RULES:
        if phase_rank < _PHASE_RANK["1.5"]:
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "business-rules-requires-phase-1.5-or-later")
        if not inputs.business_rules_executed:
            return PersistencePolicyDecision(False, PERSIST_GATE_NOT_APPROVED, "business-rules-discovery-not-executed")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_WORKSPACE_MEMORY:
        if phase_rank < _PHASE_RANK["5"]:
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "workspace-memory-requires-phase-5-or-later")
        if not inputs.gate_approved:
            return PersistencePolicyDecision(False, PERSIST_GATE_NOT_APPROVED, "workspace-memory-phase-5-not-approved")
        expected = "Persist to workspace memory: YES"
        confirmation = inputs.explicit_confirmation.strip()
        if mode == "pipeline" and confirmation != expected:
            return PersistencePolicyDecision(False, PERSIST_DISALLOWED_IN_PIPELINE, "confirmation-not-available-in-pipeline")
        if not confirmation:
            return PersistencePolicyDecision(False, PERSIST_CONFIRMATION_REQUIRED, "workspace-memory-confirmation-required")
        if confirmation != expected:
            return PersistencePolicyDecision(False, PERSIST_CONFIRMATION_INVALID, "workspace-memory-confirmation-must-be-exact")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    return PersistencePolicyDecision(True, REASON_CODE_NONE, "not-applicable")
