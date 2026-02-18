from __future__ import annotations

import pytest

from governance.application.policies.persistence_policy import (
    ARTIFACT_DECISION_PACK,
    ARTIFACT_REPO_CACHE,
    ARTIFACT_REPO_DIGEST,
    ARTIFACT_WORKSPACE_MEMORY,
    PersistencePolicyInput,
    can_write,
)


@pytest.mark.governance
def test_persistence_policy_allows_workspace_memory_when_phase5_yes_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="5-ImplementationQA",
            mode="user",
            gate_approved=True,
            business_rules_executed=True,
            explicit_confirmation="Persist to workspace memory: YES",
        )
    )
    assert decision.allowed is True
    assert decision.reason_code == "none"


@pytest.mark.governance
def test_persistence_policy_blocks_workspace_memory_without_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="5-ImplementationQA",
            mode="user",
            gate_approved=True,
            business_rules_executed=True,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERSIST_CONFIRMATION_REQUIRED"


@pytest.mark.governance
def test_persistence_policy_blocks_workspace_memory_in_pipeline_without_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="5-ImplementationQA",
            mode="pipeline",
            gate_approved=True,
            business_rules_executed=True,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERSIST_DISALLOWED_IN_PIPELINE"


@pytest.mark.governance
def test_persistence_policy_allows_workspace_memory_phase2_observations_without_confirmation():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_WORKSPACE_MEMORY,
            phase="2-Discovery",
            mode="pipeline",
            gate_approved=False,
            business_rules_executed=False,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is True
    assert decision.reason_code == "none"


@pytest.mark.governance
def test_persistence_policy_blocks_decision_pack_outside_phase21():
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=ARTIFACT_DECISION_PACK,
            phase="2-Discovery",
            mode="user",
            gate_approved=False,
            business_rules_executed=False,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERSIST_PHASE_MISMATCH"


@pytest.mark.governance
@pytest.mark.parametrize("artifact", [ARTIFACT_REPO_CACHE, ARTIFACT_REPO_DIGEST])
def test_persistence_policy_blocks_cache_and_digest_outside_phase2(artifact: str):
    decision = can_write(
        PersistencePolicyInput(
            artifact_kind=artifact,
            phase="2.1-DecisionPack",
            mode="user",
            gate_approved=False,
            business_rules_executed=False,
            explicit_confirmation="",
        )
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERSIST_PHASE_MISMATCH"
