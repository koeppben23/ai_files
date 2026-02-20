from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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


_ARTIFACT_KEY_TO_KIND = {
    "repo_cache": ARTIFACT_REPO_CACHE,
    "repo_digest": ARTIFACT_REPO_DIGEST,
    "decision_pack": ARTIFACT_DECISION_PACK,
    "business_rules_inventory": ARTIFACT_BUSINESS_RULES,
    "workspace_memory": ARTIFACT_WORKSPACE_MEMORY,
}

_DEFAULT_ALLOWED_PHASES = {
    ARTIFACT_REPO_CACHE: frozenset({"2"}),
    ARTIFACT_REPO_DIGEST: frozenset({"2"}),
    ARTIFACT_DECISION_PACK: frozenset({"2.1"}),
    ARTIFACT_BUSINESS_RULES: frozenset({"1.5"}),
    ARTIFACT_WORKSPACE_MEMORY: frozenset({"2", "4", "5", "6"}),
}

_ALLOWED_PHASES_BY_ARTIFACT: dict[str, frozenset[str]] = dict(_DEFAULT_ALLOWED_PHASES)


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


def _normalize_policy_phase_token(value: object) -> str:
    raw = str(value).strip().lower()
    if raw.startswith("phase_"):
        raw = raw[len("phase_") :]
    raw = raw.replace("_", ".")
    return normalize_phase_token(raw)


def configure_persistence_artifact_policy(policy_bundle: Mapping[str, Any] | None) -> None:
    """Configure artifact phase windows from policy-bound bundle data."""
    global _ALLOWED_PHASES_BY_ARTIFACT

    if not isinstance(policy_bundle, Mapping):
        _ALLOWED_PHASES_BY_ARTIFACT = dict(_DEFAULT_ALLOWED_PHASES)
        return

    artifacts = policy_bundle.get("artifacts")
    if not isinstance(artifacts, Mapping):
        _ALLOWED_PHASES_BY_ARTIFACT = dict(_DEFAULT_ALLOWED_PHASES)
        return

    configured = dict(_DEFAULT_ALLOWED_PHASES)
    for artifact_key, artifact_cfg in artifacts.items():
        kind = _ARTIFACT_KEY_TO_KIND.get(str(artifact_key))
        if kind is None or not isinstance(artifact_cfg, Mapping):
            continue
        phase_window = artifact_cfg.get("phase_window")
        if not isinstance(phase_window, Mapping):
            continue
        write_allowed = phase_window.get("write_allowed")
        if not isinstance(write_allowed, list):
            continue
        phase_tokens = {
            token
            for token in (_normalize_policy_phase_token(v) for v in write_allowed)
            if token
        }
        if phase_tokens:
            configured[kind] = frozenset(phase_tokens)

    _ALLOWED_PHASES_BY_ARTIFACT = configured


def _phase_allowed(artifact: str, phase_token: str) -> bool:
    allowed = _ALLOWED_PHASES_BY_ARTIFACT.get(artifact)
    if not allowed:
        return False
    if phase_token in allowed:
        return True
    if phase_token.startswith("5") and "5" in allowed:
        return True
    return False

def can_write(inputs: PersistencePolicyInput) -> PersistencePolicyDecision:
    artifact = inputs.artifact_kind.strip()
    phase_token = normalize_phase_token(inputs.phase)
    mode = inputs.mode.strip().lower()

    if artifact in {ARTIFACT_REPO_CACHE, ARTIFACT_REPO_DIGEST}:
        if not _phase_allowed(artifact, phase_token):
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "artifact-requires-phase-2")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_DECISION_PACK:
        if not _phase_allowed(artifact, phase_token):
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "artifact-requires-phase-2.1")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_BUSINESS_RULES:
        if not _phase_allowed(artifact, phase_token):
            return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "business-rules-requires-phase-1.5")
        if not inputs.business_rules_executed:
            return PersistencePolicyDecision(False, PERSIST_GATE_NOT_APPROVED, "business-rules-discovery-not-executed")
        return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed")

    if artifact == ARTIFACT_WORKSPACE_MEMORY:
        if phase_token == "2" and _phase_allowed(artifact, phase_token):
            return PersistencePolicyDecision(True, REASON_CODE_NONE, "allowed-phase2-observations")

        if not _phase_allowed(artifact, phase_token):
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
    return PersistencePolicyDecision(False, PERSIST_PHASE_MISMATCH, "unknown-artifact-kind")
