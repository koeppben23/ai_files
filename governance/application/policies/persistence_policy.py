from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from governance.domain.phase_state_machine import normalize_phase_token
from governance.domain.reason_codes import (
    PERSIST_CONFIRMATION_INVALID,
    PERSIST_CONFIRMATION_REQUIRED,
    PERSIST_DISALLOWED_IN_PIPELINE,
    PERSIST_GATE_NOT_APPROVED,
    PERSIST_ARTIFACT_UNKNOWN,
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

def can_write(inputs: PersistencePolicyInput) -> PersistencePolicyDecision:
    artifact = inputs.artifact_kind.strip()
    phase_token = normalize_phase_token(inputs.phase)
    mode = inputs.mode.strip().lower()

    if artifact in {ARTIFACT_REPO_CACHE, ARTIFACT_REPO_DIGEST}:
        if phase_token != "2":
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "artifact-requires-phase-2")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_DECISION_PACK:
        if phase_token != "2.1":
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "artifact-requires-phase-2.1")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_BUSINESS_RULES:
        if phase_token != "1.5":
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "business-rules-requires-phase-1.5")
        if not inputs.business_rules_executed:
            return PersistencePolicyDecision(False, PERSIST_GATE_NOT_APPROVED, "business-rules-discovery-not-executed")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_WORKSPACE_MEMORY:
        if phase_token == "2":
            return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed-phase2-observations")

        if phase_token not in {"5", "5.3", "5.4", "5.5", "5.6"}:
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "workspace-memory-requires-phase-2-or-phase-5-family")

        if not inputs.gate_approved:
            return PersistencePolicyDecision(False, PERSIST_GATE_NOT_APPROVED, "workspace-memory-phase-5-not-approved")

        expected = "Persist to workspace memory: YES"
        confirmation = inputs.explicit_confirmation.strip()
        if mode == "pipeline":
            return PersistencePolicyDecision(False, PERSIST_DISALLOWED_IN_PIPELINE, "confirmation-not-available-in-pipeline")
        if not confirmation:
            return PersistencePolicyDecision(False, PERSIST_CONFIRMATION_REQUIRED, "workspace-memory-confirmation-required")
        if confirmation != expected:
            return PersistencePolicyDecision(False, PERSIST_CONFIRMATION_INVALID, "workspace-memory-confirmation-must-be-exact")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    # Fail-closed: unknown artifacts must not become implicitly "allowed".
    # This prevents drift via typos/new artifact kinds bypassing policy.
    return PersistencePolicyDecision(
        False,
        PERSIST_ARTIFACT_UNKNOWN,
        "unknown-artifact-kind",
    )
